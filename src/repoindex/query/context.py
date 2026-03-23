from __future__ import annotations

import ast
import json
import re
import sqlite3
from pathlib import Path
from typing import Callable, cast

from repoindex.prompts.default import build_prompt
from repoindex.query.classifier import QueryIntent, classify_query
from repoindex.query.exact import docstring_issues, find_symbol
from repoindex.scanner import iter_project_files
from repoindex.storage import get_db_path
from repoindex.types import (
    ChannelBundle,
    ChannelName,
    ChannelResults,
    CodeContext,
    ReferenceRow,
    SymbolRow,
)

_MIN_SCORE = 1
# --- token-capped context construction ---
MAX_TOKENS = 1200
# --- cap doc issues to avoid prompt bloat ---
MAX_ISSUES = 20


def _render_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    source: str,
) -> str:
    if isinstance(node, ast.ClassDef):
        return f"{node.name}"

    try:
        params = ast.get_source_segment(source, node.args)
    except ValueError:
        params = None

    if not params:
        arg_names = [arg.arg for arg in node.args.args]
        if node.args.vararg is not None:
            arg_names.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg is not None:
            arg_names.append(f"**{node.args.kwarg.arg}")
        params = ", ".join(arg_names)

    returns = ""
    if node.returns is not None:
        try:
            ret = ast.get_source_segment(source, node.returns)
        except ValueError:
            ret = None
        if ret:
            returns = f" -> {ret}"

    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}{node.name}({params}){returns}"


def _truncate_lines(text: str | None, limit: int) -> str | None:
    if not text:
        return None

    lines = text.strip().splitlines()
    if len(lines) <= limit:
        return "\n".join(lines)

    kept = lines[:limit]
    kept.append("...")
    return "\n".join(kept)


def _snippet_from_lines(
    source_lines: list[str], lineno: int, limit: int = 5
) -> list[str]:
    start = max(lineno - 1, 0)
    end = min(start + limit, len(source_lines))
    return [line.rstrip() for line in source_lines[start:end]]


def _snippet_from_node(
    node: ast.AST,
    source_lines: list[str],
    limit: int = 5,
) -> list[str]:
    """
    Extract a compact snippet for a node using AST positions.

    Includes:
    - decorators (if present)
    - definition line
    - first body lines

    Truncated to `limit` lines.
    """
    # Determine start (include decorators if present)
    start = getattr(node, "lineno", 1) - 1

    # --- include decorators if present ---
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if node.decorator_list:
            try:
                start = min(d.lineno for d in node.decorator_list) - 1
            except (AttributeError, ValueError):
                pass

    # Determine end (best-effort)
    end = getattr(node, "end_lineno", None)
    if end is None:
        end = getattr(node, "lineno", 1)

    # Slice and truncate
    snippet = source_lines[start:end]

    # --- remove docstring if present ---
    body = getattr(node, "body", None)
    if body:
        doc = ast.get_docstring(
            cast(
                ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module, node
            ),
            clean=False,
        )
        if doc is not None and isinstance(body[0], ast.Expr):
            doc_node = body[0]

            # absolute positions
            doc_start = doc_node.lineno - 1
            doc_end = getattr(doc_node, "end_lineno", doc_start + 1)

            # snippet base offset
            snippet_start = start

            # convert to snippet-local indices
            local_start = doc_start - snippet_start
            local_end = doc_end - snippet_start

            snippet = [
                line
                for i, line in enumerate(snippet)
                if not (local_start <= i < local_end)
            ]

    # --- truncate ---
    snippet = snippet[:limit]

    return [line.rstrip() for line in snippet]


def _extract_code_context(
    root: Path,
    symbol: SymbolRow,
    cache: dict[Path, tuple[str, list[str], ast.Module]],
) -> CodeContext:
    symbol_type, _module_name, name, file_path, lineno = symbol
    path = root / file_path

    if path in cache:
        source, source_lines, tree = cache[path]
    else:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return (None, None, [])

        source_lines = source.splitlines()

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return (None, None, _snippet_from_lines(source_lines, lineno))

        cache[path] = (source, source_lines, tree)

    if symbol_type == "module":
        module_doc = ast.get_docstring(tree, clean=True)
        snippet = _snippet_from_lines(source_lines, lineno)
        return (None, _truncate_lines(module_doc, 10), snippet)

    # --- CLASS MATCH ---
    if symbol_type == "class":
        class_candidates: list[ast.ClassDef] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                class_candidates.append(node)

        if class_candidates:
            node = min(class_candidates, key=lambda n: abs(n.lineno - lineno))
            signature = _render_signature(node, source)
            docstring = ast.get_docstring(node, clean=True)
            snippet = _snippet_from_node(node, source_lines)
            return (signature, _truncate_lines(docstring, 10), snippet)

    # --- FUNCTION MATCH ---
    if symbol_type == "function":
        func_candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == name:
                    func_candidates.append(node)

        if func_candidates:
            node = min(func_candidates, key=lambda n: abs(n.lineno - lineno))
            signature = _render_signature(node, source)
            docstring = ast.get_docstring(node, clean=True)
            snippet = _snippet_from_node(node, source_lines)
            return (signature, _truncate_lines(docstring, 10), snippet)

    # --- METHOD MATCH ---
    if symbol_type == "method":
        method_candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if child.name == name:
                            method_candidates.append(child)

        if method_candidates:
            node = min(method_candidates, key=lambda n: abs(n.lineno - lineno))
            signature = _render_signature(node, source)
            docstring = ast.get_docstring(node, clean=True)
            snippet = _snippet_from_node(node, source_lines)
            return (signature, _truncate_lines(docstring, 10), snippet)

    # --- FALLBACK ---
    return (None, None, _snippet_from_lines(source_lines, lineno))


def _symbols_in_module(root: Path, module: str) -> list[SymbolRow]:
    conn = sqlite3.connect(get_db_path(root))
    try:
        rows = conn.execute(
            """
            SELECT type, module_name, name, file_path, lineno
            FROM symbol_index
            WHERE module_name = ?
            LIMIT 20
            """,
            (module,),
        ).fetchall()
    finally:
        conn.close()

    return [
        (str(t), str(m), str(n), str(f), int(lineno)) for t, m, n, f, lineno in rows
    ]


def _find_references(
    root: Path,
    name: str,
    project_files: list[Path],
    file_cache: dict[Path, list[str]] | None = None,
) -> list[ReferenceRow]:
    """
    Find references to a symbol name across indexed Python files.

    This is a simple string-based search:
    - scans only files provided in ``project_files``
    - returns (file_path, lineno)
    - skips import statements
    - limits results to avoid explosion

    Notes
    -----
    The function relies on the indexing phase to define the set of
    project files, ensuring consistency between indexing and querying.
    """
    results: list[ReferenceRow] = []
    if file_cache is None:
        file_cache = {}

    for path in project_files:
        if path in file_cache:
            lines = file_cache[path]
        else:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            file_cache[path] = lines
        try:
            rel = path.relative_to(root)
            file_path = str(rel)
        except ValueError:
            file_path = str(path)

        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()

            # --- FILTER: skip imports ---
            if stripped.startswith(("import ", "from ")):
                continue

            # simple containment check
            if name not in line:
                continue

            results.append((file_path, lineno))

            # hard cap (global)
            if len(results) >= 50:
                return results

    return results


def _tokenize(text: str) -> set[str]:
    parts = re.split(r"[^A-Za-z0-9_]+", text.lower())
    tokens: set[str] = set()

    for part in parts:
        if not part:
            continue

        tokens.add(part)
        for sub in part.split("_"):
            if sub:
                tokens.add(sub)

    return tokens


def _path_bias(file_path: str) -> int:
    """
    Lightweight ranking bias based on file location.

    Favors core source code over scripts/tests without hiding results.
    """
    if file_path.startswith("src/"):
        return 2
    if file_path.startswith("scripts/"):
        return -2
    if file_path.startswith("tests/"):
        return -1
    return 0


def _score_match(query_tokens: list[str], symbol: SymbolRow) -> int:
    symbol_type, module_name, name, _file_path, _lineno = symbol

    score = 0

    query = " ".join(query_tokens)

    # --- Exact match (very strong) ---
    if query == name:
        score += 100

    # --- Substring match ---
    elif query in name:
        score += 50

    # --- Token overlap ---
    name_tokens = _tokenize(name)
    overlap = set(query_tokens) & set(name_tokens)
    score += 10 * len(overlap)

    # --- Module signal (light) ---
    module_tokens = _tokenize(module_name)
    module_overlap = set(query_tokens) & set(module_tokens)
    score += 3 * len(module_overlap)

    # --- Type bias (very small) ---
    if symbol_type == "function":
        score += 5

    # --- Penalize private symbols ---
    if name.startswith("_"):
        score -= 20

    # --- Penalize tests ---
    if "tests" in module_name:
        score -= 15

    # --- Query intent: module (strong override) ---
    if "module" in query_tokens:
        if symbol_type == "module":
            score += 120
        else:
            score -= 40

    # --- Prefer central modules (shorter paths) ---
    if symbol_type == "module":
        depth = module_name.count(".")
        score -= depth * 5

    return score


def _format_symbol(symbol: SymbolRow, *, include_path: bool) -> str:
    symbol_type, module_name, name, file_path, lineno = symbol

    if symbol_type == "module":
        head = f"{symbol_type}: {module_name}:{lineno}"
    else:
        head = f"{symbol_type}: {module_name}.{name}:{lineno}"

    if include_path:
        try:
            rel_path = str(Path(file_path).relative_to(Path.cwd()))
        except ValueError:
            rel_path = str(file_path)
        return f"{head} ({rel_path})"
    return head


def _format_enriched_symbol(
    root: Path,
    symbol: SymbolRow,
    cache: dict[Path, tuple[str, list[str], ast.Module]],
) -> list[str]:
    symbol_type, module_name, name, file_path, lineno = symbol
    signature, docstring, snippet = _extract_code_context(root, symbol, cache)

    lines: list[str] = []

    if symbol_type == "module":
        lines.append(f"module {module_name}")
    elif signature:
        lines.append(f"{symbol_type} {signature}")
    else:
        lines.append(f"{symbol_type} {name} in {module_name}")

    try:
        rel_path = str(Path(file_path).relative_to(root))
    except ValueError:
        rel_path = str(file_path)

    lines.append(f"  File: {rel_path}")
    lines.append(f"  Line: {lineno}")

    if snippet:
        lines.append("  Snippet:")
        for line in snippet:
            lines.append(f"    {line}")

    if docstring:
        lines.append("  Docstring:")
        doc_lines = docstring.splitlines()

        MAX_DOC_LINES = 12

        for line in doc_lines[:MAX_DOC_LINES]:
            lines.append(f"    {line}")

        if len(doc_lines) > MAX_DOC_LINES:
            lines.append("    [...]")

    return lines


def _retrieve_symbol_candidates(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> ChannelResults:
    """
    Retrieve and score symbol-channel candidates for a query.

    Parameters
    ----------
    root : pathlib.Path
        Root directory of the indexed repository.
    query : str
        User query string.
    conn : sqlite3.Connection
        Active database connection.
    intent : QueryIntent
        Structured classification of the query.

    Returns
    -------
    list[tuple[float, SymbolRow]]
        Ranked candidate symbols with scores sorted by descending score.

    Notes
    -----
    This phase applies deterministic scoring only. It does not perform
    final deduplication or pruning.
    """
    matches = find_symbol(root, query, conn=conn)
    query_tokens = sorted(_tokenize(query))

    candidate_map: dict[SymbolRow, None] = {match: None for match in matches}

    search_terms = sorted({token for token in query_tokens if len(token) >= 4})

    for term in search_terms:
        rows = conn.execute(
            """
            SELECT type, module_name, name, file_path, lineno
            FROM symbol_index
            WHERE name = ?
               OR name LIKE ?
               OR module_name LIKE ?
            ORDER BY type, module_name, file_path, lineno
            LIMIT 50
            """,
            (term, f"%{term}%", f"%{term}%"),
        ).fetchall()

        for row in rows:
            candidate = (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                int(row[4]),
            )
            candidate_map[candidate] = None

    if candidate_map:
        all_candidates = sorted(
            candidate_map,
            key=lambda symbol: (symbol[1], symbol[2], symbol[3], symbol[4]),
        )
    else:
        rows = conn.execute("""
            SELECT type, module_name, name, file_path, lineno
            FROM symbol_index
            ORDER BY module_name, name, file_path, lineno
            LIMIT 200
            """).fetchall()

        all_candidates = [
            (str(t), str(m), str(n), str(f), int(lin)) for t, m, n, f, lin in rows
        ]

    target_symbol = None
    for token in sorted(query_tokens, key=len, reverse=True):
        if "_" in token or token.isidentifier():
            target_symbol = token
            break

    token_cache: dict[str, list[str]] = {}
    scored: list[tuple[float, SymbolRow]] = []

    for candidate in all_candidates:
        base_score = _score_match(query_tokens, candidate)
        score = base_score + _path_bias(candidate[3])

        if target_symbol and candidate[2] == target_symbol:
            score += 10

        if candidate[2] == query:
            score += 5

        symbol_name = candidate[2]
        module_name = candidate[1]
        symbol_type = candidate[0]

        if symbol_name.startswith("_"):
            score -= 2

        freq = sum(1 for t in query_tokens if t in symbol_name.lower())
        score += freq * 2

        if module_name.startswith("tests."):
            pass
        elif module_name.startswith("scripts."):
            pass
        else:
            score += 2

        lowered_module = module_name.lower()
        if any(x in lowered_module for x in ("cli", "scanner", "storage")):
            score -= 2

        if intent.is_identifier_query:
            if symbol_name == intent.raw:
                score += 25
            elif module_name.endswith(intent.raw):
                score += 8

        if intent.is_multi_term and symbol_type == "module":
            score += 1

        if symbol_name not in token_cache:
            token_cache[symbol_name] = list(_tokenize(symbol_name))
        candidate_tokens = token_cache[symbol_name]

        strong_tokens = [t for t in query_tokens if len(t) >= 4]

        normalized_strong_tokens: list[str] = []
        for t in strong_tokens:
            normalized_strong_tokens.append(t)
            if "_" in t:
                normalized_strong_tokens.extend(t.split("_"))

        if not any(t in candidate_tokens for t in normalized_strong_tokens):
            continue

        if score >= _MIN_SCORE:
            scored.append((float(score), candidate))

    scored.sort(reverse=True)

    if not scored:
        fallback_scored: list[tuple[float, SymbolRow]] = []

        for candidate in all_candidates:
            score = _score_match(query_tokens, candidate) + _path_bias(candidate[3])

            symbol_name = candidate[2]
            module_name = candidate[1]
            symbol_type = candidate[0]

            if intent.is_identifier_query:
                if symbol_name == intent.raw:
                    score += 25
                elif module_name.endswith(intent.raw):
                    score += 8

            if intent.is_multi_term and symbol_type == "module":
                score += 1

            fallback_scored.append((float(score), candidate))

        fallback_scored.sort(reverse=True)
        return fallback_scored

    return scored


def _retrieve_test_candidates(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> ChannelResults:
    return []


def _retrieve_script_candidates(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> ChannelResults:
    return []


def _merge_ranked_channels(
    channels: list[ChannelBundle],
) -> list[SymbolRow]:
    return _merge_ranked_channel_bundles(channels)


def _merge_ranked_channel_bundles_explain(
    bundles: list[ChannelBundle],
) -> tuple[list[SymbolRow], dict[SymbolRow, dict[str, float]]]:
    weights = _channel_weights()

    merged: dict[SymbolRow, float] = {}
    provenance: dict[SymbolRow, dict[str, float]] = {}

    for channel_name, channel in bundles:
        weight = weights.get(channel_name, 1.0)

        for score, symbol in channel:
            weighted_score = score * weight

            if symbol not in provenance:
                provenance[symbol] = {}
            provenance[symbol][channel_name] = weighted_score

            if symbol not in merged or weighted_score > merged[symbol]:
                merged[symbol] = weighted_score

    ranked = sorted(
        merged.items(),
        key=lambda item: (item[1], item[0][1], item[0][2], item[0][3], item[0][4]),
        reverse=True,
    )

    top_symbols = [symbol for symbol, _ in ranked[:10]]

    return top_symbols, provenance


def _merge_ranked_channel_bundles(
    bundles: list[ChannelBundle],
) -> list[SymbolRow]:
    top_symbols, _ = _merge_ranked_channel_bundles_explain(bundles)
    return top_symbols


def _channel_weights() -> dict[ChannelName, float]:
    return {
        "symbol": 1.0,
        "test": 1.0,
        "script": 1.0,
    }


def _channel_order() -> list[ChannelName]:
    return ["symbol", "test", "script"]


def _build_channel_bundles(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> list[ChannelBundle]:
    channel_fns = _get_channel_functions(intent)

    return [(name, fn(root, query, conn, intent)) for name, fn in channel_fns]


def _get_channel_functions(
    intent: QueryIntent,
) -> list[
    tuple[
        ChannelName,
        Callable[
            [Path, str, sqlite3.Connection, QueryIntent],
            ChannelResults,
        ],
    ]
]:
    order = _channel_order()
    registry = _channel_registry()

    all_channels = [(name, registry[name]) for name in order if name in registry]

    selected = _filter_channels_by_intent(intent, all_channels)

    return selected


def _channel_registry() -> dict[
    ChannelName,
    Callable[
        [Path, str, sqlite3.Connection, QueryIntent],
        ChannelResults,
    ],
]:
    return {
        "symbol": _retrieve_symbol_candidates,
        "test": _retrieve_test_candidates,
        "script": _retrieve_script_candidates,
    }


def _filter_channels_by_intent(
    intent: QueryIntent,
    channels: list[
        tuple[
            ChannelName,
            Callable[
                [Path, str, sqlite3.Connection, QueryIntent],
                ChannelResults,
            ],
        ]
    ],
) -> list[
    tuple[
        ChannelName,
        Callable[
            [Path, str, sqlite3.Connection, QueryIntent],
            ChannelResults,
        ],
    ]
]:
    priority = _channel_priority(intent)

    enabled = _enabled_channels(intent)

    filtered = [item for item in channels if item[0] in enabled]

    ordered = sorted(
        filtered,
        key=lambda item: priority.get(item[0], 100),
    )

    return ordered


def _enabled_channels(intent: QueryIntent) -> set[ChannelName]:
    if intent.is_test_related:
        return {
            "test",
            "symbol",
        }
    if intent.is_script_related:
        return {
            "script",
            "symbol",
        }
    return {
        "symbol",
    }


def _channel_priority(intent: QueryIntent) -> dict[ChannelName, int]:
    if intent.is_test_related:
        return {
            "test": 0,
            "symbol": 1,
            "script": 2,
        }
    if intent.is_script_related:
        return {
            "script": 0,
            "symbol": 1,
            "test": 2,
        }
    return {
        "symbol": 0,
        "test": 1,
        "script": 2,
    }


def _is_issue_query(query: str) -> bool:
    query_tokens = _tokenize(query)
    issue_tokens = {
        "doc",
        "docstring",
        "docs",
        "issue",
        "issues",
        "missing",
        "numpy",
        "section",
        "returns",
        "parameters",
    }
    return any(token in issue_tokens for token in query_tokens)


def _issue_driven_symbols(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
) -> list[SymbolRow]:
    issue_rows = docstring_issues(root, conn=conn)
    query_tokens = _tokenize(query)
    scored: dict[SymbolRow, int] = {}

    GENERIC_NAMES = {"main", "__init__", "run"}

    for issue_type, message in issue_rows:
        message_lower = message.lower()

        if not any(token in message_lower for token in query_tokens):
            continue

        head = message.split(":", 1)[0]

        # Extract symbol name deterministically
        symbol_name: str | None = None

        if head.startswith("Function "):
            symbol_name = head[len("Function ") :]

        elif head.startswith("Module "):
            symbol_name = head[len("Module ") :].split(".")[-1]

        elif head.startswith("Method "):
            parts = head[len("Method ") :].split(".")
            if len(parts) == 2:
                symbol_name = parts[1]

        if not symbol_name:
            continue

        if symbol_name in GENERIC_NAMES:
            continue

        for symbol in find_symbol(root, symbol_name, conn=conn):
            module_name = symbol[1]

            # Reject obvious noise
            if (
                module_name.startswith("tests.")
                or module_name.startswith("scripts.")
                or module_name.startswith(".")
            ):
                continue

            bonus = 3 if issue_type == "missing" else 1

            if symbol in scored:
                scored[symbol] += bonus
            else:
                scored[symbol] = bonus

    ranked = sorted(
        scored,
        key=lambda symbol: (
            -scored[symbol],
            symbol[3],
            symbol[4],
            symbol[2],
        ),
    )

    return ranked[:5]


def _collect_doc_issues_and_related(
    root: Path,
    query: str,
    top_matches: list[SymbolRow],
    conn: sqlite3.Connection,
) -> tuple[list[tuple[str, str]], list[SymbolRow]]:
    """
    Collect related docstring issues and derive additional related symbols.
    """
    issue_rows = docstring_issues(root, conn=conn)

    issue_rows_filtered: list[tuple[str, str]] = []

    symbol_names = {name for _, _, name, _, _ in top_matches if name}

    for issue_type, message in issue_rows:
        if not any(name in message for name in symbol_names):
            continue

        # --- FILTER NOISE: skip tests and scripts ---
        if "tests." in message or "scripts." in message:
            continue

        issue_rows_filtered.append((issue_type, message))

    doc_issues: list[tuple[str, str]] = issue_rows_filtered[:20]

    related_symbols: list[SymbolRow] = []

    for _, message in doc_issues:
        parts = message.split(":")[0].split()
        if len(parts) >= 2:
            symbol_name = parts[-1]
            related_symbols.extend(find_symbol(root, symbol_name, conn=conn))

    return doc_issues, related_symbols


def _is_test_file(path: str) -> bool:
    return "/tests/" in path or Path(path).name.startswith("test_")


def _dedupe_and_cap_references(
    refs: list[ReferenceRow],
    *,
    max_per_file: int = 3,
    min_line_gap: int = 5,
) -> list[ReferenceRow]:
    # group by file
    by_file: dict[str, list[int]] = {}

    for file_path, lineno in refs:
        by_file.setdefault(file_path, []).append(lineno)

    result: list[ReferenceRow] = []

    for file_path in sorted(by_file):
        lines = sorted(by_file[file_path])

        kept: list[int] = []
        last_kept: int | None = None

        for ln in lines:
            if last_kept is None or abs(ln - last_kept) >= min_line_gap:
                kept.append(ln)
                last_kept = ln

            if len(kept) >= max_per_file:
                break

        for ln in kept:
            result.append((file_path, ln))

    return result


def _expand_and_collect_references(
    root: Path,
    top_matches: list[SymbolRow],
) -> tuple[list[SymbolRow], list[ReferenceRow]]:
    """
    Perform module expansion and collect cross-module references.
    """
    # --- PHASE 4: module expansion ---
    expanded: list[SymbolRow] = []
    seen_modules: set[str] = set()

    for _, module_name, _, _, _ in top_matches:
        if module_name in seen_modules:
            continue

        seen_modules.add(module_name)

        for symbol in _symbols_in_module(root, module_name):
            name = symbol[2]

            # --- FILTER: skip internal helpers ---
            if name.startswith("_"):
                continue

            if symbol not in expanded:
                expanded.append(symbol)

    # --- REMOVE duplicates already in top_matches ---
    top_set = set(top_matches)
    expanded = [s for s in expanded if s not in top_set]

    # remove duplicates by (module, name)
    seen_keys: set[tuple[str, str]] = set()
    deduped: list[SymbolRow] = []

    for t, m, n, f, lin in expanded:
        key = (m, n)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append((t, m, n, f, lin))

    # --- FILTER NOISE: remove test and script modules ---
    filtered: list[SymbolRow] = []

    for t, m, n, f, lin in deduped:
        if m.startswith("tests.") or m.startswith("scripts."):
            continue
        filtered.append((t, m, n, f, lin))

    expanded = filtered[:20]

    symbol_names = {name for _, _, name, _, _ in top_matches if name}
    project_files = list(iter_project_files(root))

    # --- PHASE 5: cross-module references ---
    top_files = {file_path for _, _, _, file_path, _ in top_matches}

    file_cache: dict[Path, list[str]] = {}

    test_refs: list[ReferenceRow] = []
    other_refs: list[ReferenceRow] = []

    for name in symbol_names:
        for file_path, lineno in _find_references(
            root,
            name,
            project_files,
            file_cache=file_cache,
        ):
            if file_path in top_files:
                continue

            ref = (file_path, lineno)

            if _is_test_file(file_path):
                test_refs.append(ref)
            else:
                other_refs.append(ref)

    seen_refs: set[ReferenceRow] = set()
    unique_refs: list[ReferenceRow] = []

    # prioritize test references first
    for ref in test_refs + other_refs:
        if ref not in seen_refs:
            seen_refs.add(ref)
            unique_refs.append(ref)

    unique_refs = _dedupe_and_cap_references(unique_refs)
    unique_refs = unique_refs[:20]

    return expanded, unique_refs


def _prompt_symbol_line(root: Path, symbol: SymbolRow) -> str:
    symbol_type, module_name, name, file_path, lineno = symbol

    try:
        rel_path = str(Path(file_path).relative_to(root))
    except ValueError:
        rel_path = str(file_path)

    if symbol_type == "module":
        return f"- {symbol_type} {module_name} ({rel_path}:{lineno})"

    return f"- {symbol_type} {module_name}.{name} ({rel_path}:{lineno})"


def _render_agent_prompt(
    root: Path,
    query: str,
    top_matches: list[SymbolRow],
    doc_issues: list[tuple[str, str]],
    expanded: list[SymbolRow],
    unique_refs: list[ReferenceRow],
) -> str:
    return build_prompt(
        root,
        query,
        top_matches,
        doc_issues,
        expanded,
        unique_refs,
        prompt_symbol_line=_prompt_symbol_line,
        format_enriched_symbol=_format_enriched_symbol,
    )


def _approx_token_count(lines: list[str]) -> int:
    return sum(len(line.split()) for line in lines)


def _render_context(
    root: Path,
    query: str,
    top_matches: list[SymbolRow],
    doc_issues: list[tuple[str, str]],
    expanded: list[SymbolRow],
    unique_refs: list[ReferenceRow],
    *,
    confidence_map: dict[SymbolRow, float] | None = None,
    as_json: bool = False,
    as_prompt: bool = False,
    explain: bool = False,
    intent: QueryIntent | None = None,
    enabled_channels: set[ChannelName] | None = None,
    channel_priority: dict[ChannelName, int] | None = None,
    ordered_channels: list[ChannelName] | None = None,
    bundles: list[ChannelBundle] | None = None,
    provenance: dict[SymbolRow, dict[str, float]] | None = None,
) -> str:
    """
    Render final structured context output.
    """
    if as_json:
        status = "ok" if top_matches else "no_matches"
        _context_blocks: list[list[str]] = []
        _current_tokens = 0

        for s in top_matches[:5]:
            block = _format_enriched_symbol(root, s, {})
            block_tokens = _approx_token_count(block)

            if _current_tokens + block_tokens > MAX_TOKENS:
                break

            _context_blocks.append(block)
            _current_tokens += block_tokens

        result = {
            "schema_version": "1.0",
            "status": status,
            "top_matches": [
                {
                    "type": t,
                    "module": m,
                    "name": n,
                    "file": f,
                    "lineno": lin,
                    "confidence": (
                        confidence_map.get((t, m, n, f, lin), 1.0)
                        if confidence_map
                        else 1.0
                    ),
                }
                for t, m, n, f, lin in top_matches
            ],
            "doc_issues": [{"type": t, "message": m} for t, m in doc_issues],
            "context": _context_blocks,
            "module_expansion": [
                {
                    "type": t,
                    "module": m,
                    "name": n,
                    "file": f,
                    "lineno": lin,
                }
                for t, m, n, f, lin in expanded
            ],
            "references": [{"file": f, "lineno": lin} for f, lin in unique_refs],
        }

        if explain:
            explain_block: dict[str, object] = {}

            if intent:
                explain_block["intent"] = {
                    "is_identifier_query": intent.is_identifier_query,
                    "is_test_related": intent.is_test_related,
                    "is_script_related": intent.is_script_related,
                    "is_multi_term": intent.is_multi_term,
                    "raw": intent.raw,
                }

            if enabled_channels is not None:
                explain_block["enabled_channels"] = sorted(enabled_channels)

            if channel_priority is not None:
                explain_block["channel_priority"] = channel_priority

            if ordered_channels is not None:
                explain_block["ordered_channels"] = ordered_channels

            if bundles is not None:
                channel_results: dict[str, list[dict[str, object]]] = {}

                for channel_name, channel in sorted(bundles, key=lambda item: item[0]):
                    entries: list[dict[str, object]] = []

                    for score, symbol in channel[:5]:
                        symbol_type, module_name, name, _, lineno = symbol

                        entries.append(
                            {
                                "type": symbol_type,
                                "module": module_name,
                                "name": name,
                                "lineno": lineno,
                                "score": score,
                            }
                        )

                    channel_results[channel_name] = entries

                explain_block["channel_results"] = channel_results

            if provenance is not None:
                merge_entries: list[dict[str, object]] = []

                for symbol in top_matches:
                    channel_scores = provenance.get(symbol)
                    if not channel_scores:
                        continue

                    symbol_type, module_name, name, _, lineno = symbol

                    sorted_scores = sorted(
                        channel_scores.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )

                    merge_entries.append(
                        {
                            "type": symbol_type,
                            "module": module_name,
                            "name": name,
                            "lineno": lineno,
                            "scores": dict(sorted_scores),
                            "winner": sorted_scores[0][0],
                        }
                    )

                explain_block["merge"] = merge_entries

            result["explain"] = explain_block

        return json.dumps(result, indent=2)

    if as_prompt:
        return _render_agent_prompt(
            root,
            query,
            top_matches,
            doc_issues,
            expanded,
            unique_refs,
        )

    lines: list[str] = []

    if explain:
        lines.append("=== EXPLAIN: QUERY INTENT ===")
        if intent:
            lines.append(f"is_identifier_query: {intent.is_identifier_query}")
            lines.append(f"is_test_related: {intent.is_test_related}")
            lines.append(f"is_script_related: {intent.is_script_related}")
            lines.append(f"is_multi_term: {intent.is_multi_term}")
            lines.append(f"raw: {intent.raw}")

        lines.append("\n=== EXPLAIN: CHANNEL ROUTING ===")
        if enabled_channels is not None:
            lines.append(f"enabled_channels: {sorted(enabled_channels)}")
        if channel_priority is not None:
            lines.append(f"channel_priority: {channel_priority}")
        if ordered_channels is not None:
            lines.append(f"ordered_channels: {ordered_channels}")

        lines.append("")

    if explain and bundles is not None:
        lines.append("=== EXPLAIN: CHANNEL RESULTS ===")

        for channel_name, channel in bundles:
            lines.append(f"{channel_name}:")

            if not channel:
                lines.append("  (no results)")
                continue

            for score, symbol in channel[:5]:
                symbol_type, module_name, name, _, lineno = symbol

                if symbol_type == "module":
                    label = f"{module_name}:{lineno}"
                else:
                    label = f"{module_name}.{name}:{lineno}"

                lines.append(f"  {score:.2f} -> {label}")

        lines.append("")

    if explain and provenance is not None:
        lines.append("=== EXPLAIN: MERGE ===")

        for symbol in top_matches:
            symbol_type, module_name, name, _, lineno = symbol

            if symbol_type == "module":
                label = f"{module_name}:{lineno}"
            else:
                label = f"{module_name}.{name}:{lineno}"

            channel_scores = provenance.get(symbol)

            # skip symbols not produced by channels (post-processing additions)
            if not channel_scores:
                continue

            lines.append(label)

            sorted_scores = sorted(
                channel_scores.items(),
                key=lambda item: item[1],
                reverse=True,
            )

            winner = sorted_scores[0][0]

            for channel_name, score in sorted_scores:
                lines.append(f"  {channel_name}: {score:.2f}")

            lines.append(f"  winner: {winner}")

        lines.append("")

    lines.append("=== TOP MATCHES ===")
    if not top_matches:
        lines.append("No direct symbol matches found.")
    else:
        for symbol in top_matches:
            lines.append(_format_symbol(symbol, include_path=True))

    lines.append("\n=== RELATED DOCSTRING ISSUES ===")
    if not doc_issues:
        lines.append("No related docstring issues.")
    else:
        for issue_type, message in doc_issues:
            if message.startswith("Module ") and message.endswith("Missing docstring"):
                message = message.replace(
                    "Missing docstring",
                    "Missing module-level docstring",
                )
            lines.append(f"{issue_type}: {message}")

    lines.append("\n=== SUGGESTED CONTEXT ===")
    cache: dict[Path, tuple[str, list[str], ast.Module]] = {}
    for symbol in top_matches[:5]:
        lines.extend(_format_enriched_symbol(root, symbol, cache))

    lines.append("\n=== MODULE EXPANSION ===")
    if not expanded:
        lines.append("No module expansion available.")
    else:
        for symbol in expanded:
            lines.append(_format_symbol(symbol, include_path=False))

    lines.append("\n=== CROSS-MODULE REFERENCES ===")
    if not unique_refs:
        lines.append("No cross-module references found.")
    else:
        for file_path, lineno in unique_refs:
            try:
                rel_path = str(Path(file_path).relative_to(root))
            except ValueError:
                rel_path = str(file_path)

            lines.append(f"{rel_path}:{lineno}")

    return "\n".join(lines)


def context_for(
    root: Path,
    query: str,
    *,
    as_json: bool = False,
    as_prompt: bool = False,
    explain: bool = False,
) -> str:
    """
    Build a structured context block for a given query.

    Parameters
    ----------
    root : pathlib.Path
        Root directory of the indexed repository.
    query : str
        Query string used to retrieve relevant symbols and context.

    Returns
    -------
    str
        Structured text block containing:
        - top symbol matches
        - related docstring issues
        - enriched code context
        - module expansion
        - cross-module references

    Notes
    -----
    The output is optimized for LLM consumption and follows a
    deterministic section-based layout. Query classification is
    performed before retrieval and passed into the scoring phase.
    """
    conn = sqlite3.connect(get_db_path(root))
    intent: QueryIntent = classify_query(query)

    # --- PHASE 1+2: candidate retrieval + scoring ---
    bundles = _build_channel_bundles(root, query, conn, intent)

    if explain:
        top_matches, provenance = _merge_ranked_channel_bundles_explain(bundles)
        enabled = _enabled_channels(intent)
        priority = _channel_priority(intent)
        ordered_channels = [name for name, _ in _get_channel_functions(intent)]
    else:
        top_matches = _merge_ranked_channels(bundles)
        enabled = None
        priority = None
        ordered_channels = None

    # --- confidence estimation (lightweight, deterministic) ---
    confidence_map: dict[SymbolRow, float] = {}

    query_tokens = list(_tokenize(query))

    for rank, symbol in enumerate(top_matches):
        base = 1.0 - (rank / max(len(top_matches), 1))
        name = symbol[2].lower()
        overlap = sum(1 for t in query_tokens if t in name)

        confidence = base + (0.1 * overlap)

        if confidence > 1.0:
            confidence = 1.0

        confidence_map[symbol] = confidence

    # --- PHASE 2B: issue-driven candidate enrichment ---
    if _is_issue_query(query):
        for symbol in _issue_driven_symbols(root, query, conn):
            if symbol not in top_matches:
                top_matches.append(symbol)

    top_matches = top_matches[:10]

    # --- PHASE 2C: remove module entries
    # if same module already represented by functions ---
    modules_with_functions = {
        module for t, module, name, _, _ in top_matches if t != "module"
    }

    filtered_matches: list[SymbolRow] = []

    for sym in top_matches:
        t, module, _, _, _ = sym
        if t == "module" and module in modules_with_functions:
            continue
        filtered_matches.append(sym)

    top_matches = filtered_matches

    if not top_matches:
        if as_json:
            result = _render_context(
                root,
                query,
                [],
                [],
                [],
                [],
                as_json=True,
                explain=explain,
            )
            conn.close()
            return result

        if as_prompt:
            result = _render_context(
                root,
                query,
                [],
                [],
                [],
                [],
                as_prompt=True,
                explain=explain,
            )
            conn.close()
            return result

        conn.close()
        return "No relevant matches found."

    # --- PHASE 3: related docstring issues ---
    doc_issues, related_symbols = _collect_doc_issues_and_related(
        root,
        query,
        top_matches,
        conn,
    )

    doc_issues = doc_issues[:MAX_ISSUES]

    for match in related_symbols:
        if match not in top_matches:
            top_matches.append(match)

    top_matches = top_matches[:10]

    # --- PHASE 4+5: module expansion + references ---
    expanded, unique_refs = _expand_and_collect_references(
        root,
        top_matches,
    )

    # --- PHASE 6: rendering ---
    result = _render_context(
        root,
        query,
        top_matches,
        doc_issues,
        expanded,
        unique_refs,
        confidence_map=confidence_map,
        as_json=as_json,
        as_prompt=as_prompt,
        explain=explain,
        intent=intent,
        enabled_channels=enabled,
        channel_priority=priority,
        ordered_channels=ordered_channels,
        bundles=bundles if explain else None,
        provenance=provenance if explain else None,
    )
    conn.close()
    return result
