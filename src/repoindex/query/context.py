"""Context assembly and rendering for repoindex query results."""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from pathlib import Path
from typing import Callable, cast

from repoindex._version import version as __version__
from repoindex.prompts.default import build_prompt
from repoindex.query.classifier import QueryIntent, classify_query
from repoindex.query.exact import (
    docstring_issues,
    find_call_edges,
    find_callable_refs,
    find_logical_symbols,
    find_symbol,
    logical_symbol_name,
)
from repoindex.scanner import iter_project_files
from repoindex.semantic.search import embedding_candidates
from repoindex.storage import get_db_path
from repoindex.types import (
    ChannelBundle,
    ChannelName,
    ChannelResults,
    CodeContext,
    ReferenceRow,
    SymbolRow,
)

# Current schema version
SCHEMA_VERSION = "1.1"
# Minimum accepted score
_MIN_SCORE = 1
# Maximum number of rows inspected by the symbol fallback scan.
SYMBOL_FALLBACK_SCAN_LIMIT = 200
# Maximum number of rows retrieved for a token search term.
SYMBOL_TERM_MATCH_LIMIT = 50
# Maximum number of rows inspected by the semantic channel.
SEMANTIC_SCAN_LIMIT = 500
# Maximum number of semantic results returned.
SEMANTIC_RESULT_LIMIT = 50
# Maximum number of embedding results returned.
EMBEDDING_RESULT_LIMIT = 50
# Maximum number of merged symbols returned.
MERGE_RESULT_LIMIT = 10
# --- token-capped context construction ---
MAX_TOKENS = 1200
# Number of source lines to include in extracted snippets.
SNIPPET_LINE_LIMIT = 6
# Maximum number of lines shown for extracted docstrings in code context.
DOCSTRING_PREVIEW_LINE_LIMIT = 10
# Maximum number of displayed docstring lines in enriched symbol blocks.
DISPLAY_DOCSTRING_LINE_LIMIT = 12
# Maximum number of enriched symbols rendered in text and prompt output.
ENRICHED_CONTEXT_LIMIT = 5
# --- cap doc issues to avoid prompt bloat ---
MAX_ISSUES = 20
# --- weight for semantic consolidation
SEMANTIC_WEIGHT = 0.3
# Minimum accepted embedding similarity.
EMBEDDING_MIN_SCORE = 0.2
CHANNEL_WEIGHTS: dict[ChannelName, float] = {
    "symbol": 1.0,
    "embedding": 1.0,
    "semantic": 1.0,
    "test": 1.0,
    "script": 1.0,
}


def _symbol_sort_key(symbol: SymbolRow) -> tuple[str, str, str, int, str]:
    """
    Return a deterministic ascending sort key for a symbol row.

    Parameters
    ----------
    symbol : repoindex.types.SymbolRow
        Symbol row to normalize into a sortable key.

    Returns
    -------
    tuple[str, str, str, int, str]
        Deterministic ascending key based on module, name, file, line, and type.
    """
    symbol_type, module_name, name, file_path, lineno = symbol
    return (module_name, name, file_path, lineno, symbol_type)


def _scored_symbol_sort_key(
    item: tuple[float, SymbolRow],
) -> tuple[float, str, str, str, int, str]:
    """
    Return a deterministic sort key for scored symbols.

    Parameters
    ----------
    item : tuple[float, repoindex.types.SymbolRow]
        Score and symbol pair to normalize.

    Returns
    -------
    tuple[float, str, str, str, int, str]
        Sort key ordering by descending score and ascending symbol identity.
    """
    score, symbol = item
    module_name, name, file_path, lineno, symbol_type = _symbol_sort_key(symbol)
    return (-score, module_name, name, file_path, lineno, symbol_type)


def _dedupe_channel_results(channel: ChannelResults) -> ChannelResults:
    """
    Remove duplicate symbols from a single channel while keeping best rank.

    Parameters
    ----------
    channel : repoindex.types.ChannelResults
        Ranked results emitted by one retrieval channel.

    Returns
    -------
    repoindex.types.ChannelResults
        Deduplicated channel results preserving the first occurrence of each
        symbol.
    """
    seen: set[SymbolRow] = set()
    deduped: ChannelResults = []

    for score, symbol in channel:
        if symbol in seen:
            continue
        seen.add(symbol)
        deduped.append((score, symbol))

    return deduped


def _render_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    source: str,
) -> str:
    """
    Render a compact signature string for a class or callable node.

    Parameters
    ----------
    node : ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        AST node to render.
    source : str
        Source text used to recover argument and return annotations.

    Returns
    -------
    str
        Compact display signature for the supplied node.
    """
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
    """
    Truncate multiline text to a fixed number of lines.

    Parameters
    ----------
    text : str | None
        Text block to truncate.
    limit : int
        Maximum number of lines to retain before appending an ellipsis line.

    Returns
    -------
    str | None
        Truncated text, or ``None`` when the input is empty.
    """
    if not text:
        return None

    lines = text.strip().splitlines()
    if len(lines) <= limit:
        return "\n".join(lines)

    kept = lines[:limit]
    kept.append("...")
    return "\n".join(kept)


def _snippet_from_lines(
    source_lines: list[str], lineno: int, limit: int = SNIPPET_LINE_LIMIT
) -> list[str]:
    """
    Slice a fixed-size snippet from raw source lines.

    Parameters
    ----------
    source_lines : list[str]
        Source file split into lines.
    lineno : int
        One-based line number at which the snippet should start.
    limit : int, optional
        Maximum number of lines to return.

    Returns
    -------
    list[str]
        Right-stripped source lines for the requested slice.
    """
    start = max(lineno - 1, 0)
    end = min(start + limit, len(source_lines))
    return [line.rstrip() for line in source_lines[start:end]]


def _normalize_snippet_lines(lines: list[str], limit: int) -> list[str]:
    """
    Normalize snippet lines for readable deterministic display.

    Parameters
    ----------
    lines : list[str]
        Raw snippet lines.
    limit : int
        Maximum number of normalized lines to retain.

    Returns
    -------
    list[str]
        Snippet lines with trailing whitespace removed, edge blanks trimmed,
        and repeated blank lines collapsed.
    """
    normalized: list[str] = []
    previous_blank = False

    for raw_line in lines:
        line = raw_line.rstrip()
        is_blank = line == ""

        if is_blank and previous_blank:
            continue

        normalized.append(line)
        previous_blank = is_blank

    while normalized and normalized[0] == "":
        normalized.pop(0)

    while normalized and normalized[-1] == "":
        normalized.pop()

    return normalized[:limit]


def _snippet_from_node(
    node: ast.AST,
    source_lines: list[str],
    limit: int = SNIPPET_LINE_LIMIT,
) -> list[str]:
    """
    Extract a compact snippet for a node using AST positions.

    Parameters
    ----------
    node : ast.AST
        AST node whose source snippet should be extracted.
    source_lines : list[str]
        Source file split into lines.
    limit : int, optional
        Maximum number of snippet lines to retain.

    Returns
    -------
    list[str]
        Normalized snippet lines for the node.

    Notes
    -----
    Decorators are included when present. Leading docstring blocks are removed
    from the snippet so the reader sees executable structure first.
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
    return _normalize_snippet_lines(snippet, limit)


def _extract_code_context(
    root: Path,
    symbol: SymbolRow,
    cache: dict[Path, tuple[str, list[str], ast.Module]],
) -> CodeContext:
    """
    Extract signature, docstring, and snippet data for a symbol.

    Parameters
    ----------
    root : pathlib.Path
        Repository root used to resolve file paths.
    symbol : repoindex.types.SymbolRow
        Indexed symbol row to expand.
    cache : dict[pathlib.Path, tuple[str, list[str], ast.Module]]
        Parsed-file cache shared across multiple lookups.

    Returns
    -------
    repoindex.types.CodeContext
        Signature, truncated docstring, and code snippet for the symbol.
    """
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
        return (
            None,
            _truncate_lines(module_doc, DOCSTRING_PREVIEW_LINE_LIMIT),
            snippet,
        )

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
            return (
                signature,
                _truncate_lines(docstring, DOCSTRING_PREVIEW_LINE_LIMIT),
                snippet,
            )

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
            return (
                signature,
                _truncate_lines(docstring, DOCSTRING_PREVIEW_LINE_LIMIT),
                snippet,
            )

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
            return (
                signature,
                _truncate_lines(docstring, DOCSTRING_PREVIEW_LINE_LIMIT),
                snippet,
            )

    # --- FALLBACK ---
    return (None, None, _snippet_from_lines(source_lines, lineno))


def _symbols_in_module(root: Path, module: str) -> list[SymbolRow]:
    """
    Retrieve indexed symbols belonging to a module.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    module : str
        Dotted module name to expand.

    Returns
    -------
    list[repoindex.types.SymbolRow]
        Up to twenty indexed symbols from the requested module.
    """
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

    Parameters
    ----------
    root : pathlib.Path
        Repository root used to relativize file paths.
    name : str
        Symbol name to search for.
    project_files : list[pathlib.Path]
        Indexed project files to scan.
    file_cache : dict[pathlib.Path, list[str]] | None, optional
        Optional in-memory file cache reused across scans.

    Returns
    -------
    list[repoindex.types.ReferenceRow]
        Reference locations as ``(file_path, lineno)`` tuples.

    Notes
    -----
    The function relies on the indexing phase to define the set of
    project files, ensuring consistency between indexing and querying. It uses
    simple string containment, skips import statements, and caps the total
    number of returned hits.
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
    """
    Tokenize text into lowercased alphanumeric and underscore fragments.

    Parameters
    ----------
    text : str
        Input text to split.

    Returns
    -------
    set[str]
        Unique normalized tokens extracted from the input.
    """
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

    Parameters
    ----------
    file_path : str
        Indexed file path for the candidate symbol.

    Returns
    -------
    int
        Small additive score bias based on the file location.

    Notes
    -----
    The bias prefers source files over scripts and tests without suppressing
    those results entirely.
    """
    parts = Path(file_path).parts

    if "src" in parts:
        return 2
    if "scripts" in parts:
        return -2
    if "tests" in parts:
        return -1
    return 0


def _score_match(query_tokens: list[str], symbol: SymbolRow) -> int:
    """
    Score a symbol candidate against tokenized query text.

    Parameters
    ----------
    query_tokens : list[str]
        Normalized query tokens.
    symbol : repoindex.types.SymbolRow
        Candidate symbol row to score.

    Returns
    -------
    int
        Deterministic relevance score for the candidate.
    """
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
    """
    Format a symbol row for human-readable output.

    Parameters
    ----------
    symbol : repoindex.types.SymbolRow
        Symbol row to render.
    include_path : bool
        Whether to append a file path suffix.

    Returns
    -------
    str
        Single-line textual representation of the symbol.
    """
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
    """
    Format a symbol with location, snippet, and docstring details.

    Parameters
    ----------
    root : pathlib.Path
        Repository root used to relativize paths.
    symbol : repoindex.types.SymbolRow
        Symbol row to render.
    cache : dict[pathlib.Path, tuple[str, list[str], ast.Module]]
        Parsed-file cache shared across multiple symbols.

    Returns
    -------
    list[str]
        Multi-line textual block describing the symbol.
    """
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

        for line in doc_lines[:DISPLAY_DOCSTRING_LINE_LIMIT]:
            lines.append(f"    {line}")

        if len(doc_lines) > DISPLAY_DOCSTRING_LINE_LIMIT:
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
            LIMIT ?
            """,
            (term, f"%{term}%", f"%{term}%", SYMBOL_TERM_MATCH_LIMIT),
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
        rows = conn.execute(
            """
            SELECT type, module_name, name, file_path, lineno
            FROM symbol_index
            ORDER BY module_name, name, file_path, lineno
            LIMIT ?
            """,
            (SYMBOL_FALLBACK_SCAN_LIMIT,),
        ).fetchall()
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

    scored.sort(key=_scored_symbol_sort_key)

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

        fallback_scored.sort(key=_scored_symbol_sort_key)
        return fallback_scored

    return scored


def _retrieve_test_candidates(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> ChannelResults:
    """
    Retrieve candidates for the test channel.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing indexed files.
    query : str
        User query string.
    conn : sqlite3.Connection
        Open database connection.
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification.

    Returns
    -------
    repoindex.types.ChannelResults
        Empty channel results. Test-specific retrieval is not implemented.
    """
    return []


def _retrieve_script_candidates(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> ChannelResults:
    """
    Retrieve candidates for the script channel.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing indexed files.
    query : str
        User query string.
    conn : sqlite3.Connection
        Open database connection.
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification.

    Returns
    -------
    repoindex.types.ChannelResults
        Empty channel results. Script-specific retrieval is not implemented.
    """
    return []


def _merge_ranked_channels(
    channels: list[ChannelBundle],
) -> list[SymbolRow]:
    """
    Merge ranked channels into a single ordered symbol list.

    Parameters
    ----------
    channels : list[repoindex.types.ChannelBundle]
        Ranked channel results to combine.

    Returns
    -------
    list[repoindex.types.SymbolRow]
        Top merged symbol rows.
    """
    return _merge_ranked_channel_bundles(channels)


def _merge_ranked_channel_bundles_explain(
    bundles: list[ChannelBundle],
) -> tuple[list[SymbolRow], dict[SymbolRow, dict[str, float]]]:
    """
    Merge channel bundles while preserving per-channel score provenance.

    Parameters
    ----------
    bundles : list[repoindex.types.ChannelBundle]
        Ranked channel bundles to combine.

    Returns
    -------
    tuple[
        list[repoindex.types.SymbolRow],
        dict[repoindex.types.SymbolRow, dict[str, float]],
    ]
        Top merged symbols and a provenance map keyed by symbol.
    """
    weights = _channel_weights()

    merged: dict[SymbolRow, float] = {}
    provenance: dict[SymbolRow, dict[str, float]] = {}

    for channel_name, channel in sorted(bundles, key=lambda item: item[0]):
        weight = weights.get(channel_name, 1.0)
        deduped_channel = _dedupe_channel_results(channel)

        for rank, (score, symbol) in enumerate(deduped_channel):
            weighted_score = score * weight

            # --- keep provenance EXACTLY as before ---
            if symbol not in provenance:
                provenance[symbol] = {}
            provenance[symbol][channel_name] = weighted_score

            # --- RRF merge ---
            rrf = weight * (1.0 / (rank + 1))

            if symbol not in merged:
                merged[symbol] = 0.0

            merged[symbol] += rrf

    ranked = sorted(
        merged.items(),
        key=lambda item: (-item[1], *_symbol_sort_key(item[0])),
    )

    top_symbols = [symbol for symbol, _ in ranked[:MERGE_RESULT_LIMIT]]

    return top_symbols, provenance


def _merge_ranked_channel_bundles(
    bundles: list[ChannelBundle],
) -> list[SymbolRow]:
    """
    Merge ranked channel bundles without returning provenance details.

    Parameters
    ----------
    bundles : list[repoindex.types.ChannelBundle]
        Ranked channel bundles to combine.

    Returns
    -------
    list[repoindex.types.SymbolRow]
        Top merged symbol rows.
    """
    top_symbols, _ = _merge_ranked_channel_bundles_explain(bundles)
    return top_symbols


def _channel_weights() -> dict[ChannelName, float]:
    """
    Return channel weights used during rank fusion.

    Parameters
    ----------
    None

    Returns
    -------
    dict[repoindex.types.ChannelName, float]
        Weight per retrieval channel.
    """
    return dict(CHANNEL_WEIGHTS)


def _channel_order() -> list[ChannelName]:
    """
    Return the default channel evaluation order.

    Parameters
    ----------
    None

    Returns
    -------
    list[repoindex.types.ChannelName]
        Channel names in evaluation order.
    """
    return ["symbol", "embedding", "semantic", "test", "script"]


def _build_channel_bundles(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> list[ChannelBundle]:
    """
    Execute the enabled retrieval channels for a query.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing indexed files.
    query : str
        User query string.
    conn : sqlite3.Connection
        Open database connection.
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification.

    Returns
    -------
    list[repoindex.types.ChannelBundle]
        Channel names paired with their ranked results.
    """
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
    """
    Resolve enabled channel functions for a query intent.

    Parameters
    ----------
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification.

    Returns
    -------
    list[
        tuple[
            repoindex.types.ChannelName,
            collections.abc.Callable[
                [
                    pathlib.Path,
                    str,
                    sqlite3.Connection,
                    repoindex.query.classifier.QueryIntent,
                ],
                repoindex.types.ChannelResults,
            ],
        ]
    ]
        Ordered channel names and their retrieval callables.
    """
    order = _channel_order()
    registry = _channel_registry()

    all_channels = [(name, registry[name]) for name in order if name in registry]

    selected = _filter_channels_by_intent(intent, all_channels)

    return selected


def _retrieve_semantic_candidates(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> ChannelResults:
    """
    Deterministic semantic channel with independent candidate retrieval.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing indexed files. The current implementation
        does not need it directly.
    query : str
        User query string.
    conn : sqlite3.Connection
        Open database connection.
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification. The current implementation does not
        use it directly.

    Returns
    -------
    repoindex.types.ChannelResults
        Ranked semantic candidates for the query.

    Notes
    -----
    The channel is deterministic and independent from the symbol channel. It
    scores token overlap against symbol names, module names, and optional
    docstring text when that auxiliary table exists.
    """

    del root, intent

    tokens = [t.lower() for t in _tokenize(query) if len(t) >= 3]
    if not tokens:
        return []

    rows = conn.execute(
        """
        SELECT type, module_name, name, file_path, lineno
        FROM symbol_index
        ORDER BY module_name, name, file_path, lineno
        LIMIT ?
        """,
        (SEMANTIC_SCAN_LIMIT,),
    ).fetchall()

    results: ChannelResults = []

    for row in rows:
        symbol = (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            int(row[4]),
        )

        symbol_type, module_name, name, _file_path, _lineno = symbol

        text_parts = [module_name.lower(), name.lower()]

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT docstring FROM docstrings WHERE module=? AND name=?",
                (module_name, name),
            )
            doc_row = cursor.fetchone()
            if doc_row and doc_row[0]:
                text_parts.append(str(doc_row[0]).lower())
        except sqlite3.OperationalError:
            # docstrings table may not exist depending on index version
            pass

        semantic_score = 0.0

        for token in tokens:
            if token in name.lower():
                semantic_score += 3.0
            elif token in module_name.lower():
                semantic_score += 2.0
            elif any(token in part for part in text_parts):
                semantic_score += 1.0

        if semantic_score == 0.0:
            continue

        if symbol_type == "function":
            semantic_score += 0.5

        if name.startswith("_"):
            semantic_score -= 1.0

        if module_name.startswith("tests."):
            semantic_score -= 0.5

        if semantic_score >= SEMANTIC_WEIGHT:
            results.append((semantic_score, symbol))

    results.sort(key=_scored_symbol_sort_key)

    return results[:SEMANTIC_RESULT_LIMIT]


def _retrieve_embedding_candidates(
    root: Path,
    query: str,
    conn: sqlite3.Connection,
    intent: QueryIntent,
) -> ChannelResults:
    """
    Retrieve ranked candidates from the stored embedding channel.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    query : str
        User query string.
    conn : sqlite3.Connection
        Open database connection.
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification. The current implementation does not
        use it directly.

    Returns
    -------
    repoindex.types.ChannelResults
        Ranked embedding-channel candidates for the query.
    """
    del intent
    return embedding_candidates(
        root,
        query,
        limit=EMBEDDING_RESULT_LIMIT,
        min_score=EMBEDDING_MIN_SCORE,
        conn=conn,
    )


def _channel_registry() -> dict[
    ChannelName,
    Callable[
        [Path, str, sqlite3.Connection, QueryIntent],
        ChannelResults,
    ],
]:
    """
    Return the retrieval function registry keyed by channel name.

    Parameters
    ----------
    None

    Returns
    -------
    dict[
        repoindex.types.ChannelName,
        collections.abc.Callable[
            [
                pathlib.Path,
                str,
                sqlite3.Connection,
                repoindex.query.classifier.QueryIntent,
            ],
            repoindex.types.ChannelResults,
        ],
    ]
        Mapping from channel names to retrieval functions.
    """
    return {
        "symbol": _retrieve_symbol_candidates,
        "embedding": _retrieve_embedding_candidates,
        "test": _retrieve_test_candidates,
        "script": _retrieve_script_candidates,
        "semantic": _retrieve_semantic_candidates,
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
    """
    Filter and order channels according to query intent.

    Parameters
    ----------
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification.
    channels : list[
        tuple[
            repoindex.types.ChannelName,
            collections.abc.Callable[
                [
                    pathlib.Path,
                    str,
                    sqlite3.Connection,
                    repoindex.query.classifier.QueryIntent,
                ],
                repoindex.types.ChannelResults,
            ],
        ]
    ]
        Candidate channels to filter and order.

    Returns
    -------
    list[
        tuple[
            repoindex.types.ChannelName,
            collections.abc.Callable[
                [
                    pathlib.Path,
                    str,
                    sqlite3.Connection,
                    repoindex.query.classifier.QueryIntent,
                ],
                repoindex.types.ChannelResults,
            ],
        ]
    ]
        Enabled channels in priority order.
    """
    priority = _channel_priority(intent)

    enabled = _enabled_channels(intent)

    filtered = [item for item in channels if item[0] in enabled]

    ordered = sorted(
        filtered,
        key=lambda item: priority.get(item[0], 100),
    )

    return ordered


def _enabled_channels(intent: QueryIntent) -> set[ChannelName]:
    """
    Return the set of channels enabled for an intent.

    Parameters
    ----------
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification.

    Returns
    -------
    set[repoindex.types.ChannelName]
        Enabled retrieval channels.
    """
    if intent.is_test_related:
        return {
            "test",
            "symbol",
            "embedding",
            "semantic",
        }
    if intent.is_script_related:
        return {
            "script",
            "symbol",
            "embedding",
            "semantic",
        }
    return {
        "symbol",
        "embedding",
        "semantic",
    }


def _channel_priority(intent: QueryIntent) -> dict[ChannelName, int]:
    """
    Return channel priority values for an intent.

    Parameters
    ----------
    intent : repoindex.query.classifier.QueryIntent
        Structured query classification.

    Returns
    -------
    dict[repoindex.types.ChannelName, int]
        Lower values indicate higher routing priority.
    """
    if intent.is_test_related:
        return {
            "test": 0,
            "symbol": 1,
            "embedding": 2,
            "script": 3,
        }
    if intent.is_script_related:
        return {
            "script": 0,
            "symbol": 1,
            "embedding": 2,
            "test": 3,
        }
    return {
        "symbol": 0,
        "embedding": 1,
        "semantic": 2,
        "test": 3,
        "script": 4,
    }


def _is_issue_query(query: str) -> bool:
    """
    Check whether a query targets documentation issues.

    Parameters
    ----------
    query : str
        User query string.

    Returns
    -------
    bool
        ``True`` when the query mentions issue-oriented documentation terms.
    """
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
    """
    Rank symbols that are implicated by matching docstring issues.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    query : str
        User query string.
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    list[repoindex.types.SymbolRow]
        Small set of issue-related symbols ordered by heuristic score.
    """
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

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    query : str
        Original user query.
    top_matches : list[repoindex.types.SymbolRow]
        Primary ranked symbols for the query.
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    tuple[list[tuple[str, str]], list[repoindex.types.SymbolRow]]
        Related docstring issue rows and derived related symbols.
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
    """
    Check whether a path looks like a test file.

    Parameters
    ----------
    path : str
        File path to classify.

    Returns
    -------
    bool
        ``True`` when the path looks like a pytest-style test module.
    """
    path_obj = Path(path)
    return "tests" in path_obj.parts or path_obj.name.startswith("test_")


def _dedupe_and_cap_references(
    refs: list[ReferenceRow],
    *,
    max_per_file: int = 3,
    min_line_gap: int = 5,
) -> list[ReferenceRow]:
    """
    Dedupe reference hits and cap density per file.

    Parameters
    ----------
    refs : list[repoindex.types.ReferenceRow]
        Raw reference hits to reduce.
    max_per_file : int, optional
        Maximum number of references retained per file.
    min_line_gap : int, optional
        Minimum spacing between retained references in the same file.

    Returns
    -------
    list[repoindex.types.ReferenceRow]
        Reduced reference hits ordered by file and line number.
    """
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
    conn: sqlite3.Connection,
) -> tuple[list[SymbolRow], list[ReferenceRow]]:
    """
    Perform module expansion and collect cross-module references.

    Parameters
    ----------
    root : pathlib.Path
        Repository root used for file discovery and path normalization.
    top_matches : list[repoindex.types.SymbolRow]
        Primary ranked symbols for the query.
    conn : sqlite3.Connection
        Open database connection reused for graph lookups and symbol
        expansion.

    Returns
    -------
    tuple[list[repoindex.types.SymbolRow], list[repoindex.types.ReferenceRow]]
        Expanded related symbols and cross-module reference locations.

    Notes
    -----
    Expansion excludes private helpers and removes test or script modules to
    keep the final context focused on reusable project code. It also uses
    stored call edges and callable references to pull in cross-module related
    symbols around the primary matches.
    """
    expanded: list[SymbolRow] = []
    seen_symbols: set[SymbolRow] = set(top_matches)

    def add_related_symbol(symbol: SymbolRow) -> None:
        symbol_type, module_name, name, _file_path, _lineno = symbol
        if symbol in seen_symbols:
            return
        if name.startswith("_"):
            return
        if symbol_type == "module" and module_name.startswith(("tests.", "scripts.")):
            return
        if module_name.startswith(("tests.", "scripts.")):
            return
        seen_symbols.add(symbol)
        expanded.append(symbol)

    # --- PHASE 4A: graph-based expansion ---
    for symbol in top_matches:
        symbol_type, module_name, _name, _file_path, _lineno = symbol
        if symbol_type not in {"function", "method"}:
            continue

        logical_name = logical_symbol_name(root, symbol, conn=conn)

        outgoing_edges = find_call_edges(
            root,
            logical_name,
            module=module_name,
            conn=conn,
        )
        incoming_edges = find_call_edges(
            root,
            logical_name,
            module=module_name,
            incoming=True,
            conn=conn,
        )
        outgoing_refs = find_callable_refs(
            root,
            logical_name,
            module=module_name,
            conn=conn,
        )
        incoming_refs = find_callable_refs(
            root,
            logical_name,
            module=module_name,
            incoming=True,
            conn=conn,
        )

        for (
            _caller_module,
            _caller_name,
            callee_module,
            callee_name,
            resolved,
        ) in outgoing_edges:
            if not resolved or callee_module is None or callee_name is None:
                continue
            for related in find_logical_symbols(
                root,
                callee_module,
                callee_name,
                conn=conn,
            ):
                add_related_symbol(related)

        for (
            caller_module,
            caller_name,
            _callee_module,
            _callee_name,
            resolved,
        ) in incoming_edges:
            if not resolved:
                continue
            for related in find_logical_symbols(
                root,
                caller_module,
                caller_name,
                conn=conn,
            ):
                add_related_symbol(related)

        for (
            _owner_module,
            _owner_name,
            target_module,
            target_name,
            resolved,
        ) in outgoing_refs:
            if not resolved or target_module is None or target_name is None:
                continue
            for related in find_logical_symbols(
                root,
                target_module,
                target_name,
                conn=conn,
            ):
                add_related_symbol(related)

        for (
            owner_module,
            owner_name,
            _target_module,
            _target_name,
            resolved,
        ) in incoming_refs:
            if not resolved:
                continue
            for related in find_logical_symbols(
                root,
                owner_module,
                owner_name,
                conn=conn,
            ):
                add_related_symbol(related)

    # --- PHASE 4B: module expansion ---
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

            add_related_symbol(symbol)

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
    """
    Render a one-line symbol entry for agent prompts.

    Parameters
    ----------
    root : pathlib.Path
        Repository root used to relativize paths.
    symbol : repoindex.types.SymbolRow
        Symbol row to render.

    Returns
    -------
    str
        Prompt-friendly single-line symbol description.
    """
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
    """
    Render the agent prompt variant of the query context.

    Parameters
    ----------
    root : pathlib.Path
        Repository root used to relativize paths.
    query : str
        Original user query.
    top_matches : list[repoindex.types.SymbolRow]
        Primary ranked matches.
    doc_issues : list[tuple[str, str]]
        Related docstring issues.
    expanded : list[repoindex.types.SymbolRow]
        Secondary symbols collected by module expansion.
    unique_refs : list[repoindex.types.ReferenceRow]
        Cross-reference locations for the selected symbols.

    Returns
    -------
    str
        Prompt-formatted query context.
    """
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
    """
    Approximate token count using whitespace splitting.

    Parameters
    ----------
    lines : list[str]
        Lines whose token count should be estimated.

    Returns
    -------
    int
        Approximate token count.
    """
    return sum(len(line.split()) for line in lines)


def _render_context_json(
    root: Path,
    top_matches: list[SymbolRow],
    doc_issues: list[tuple[str, str]],
    expanded: list[SymbolRow],
    unique_refs: list[ReferenceRow],
    *,
    confidence_map: dict[SymbolRow, float] | None = None,
    explain: bool = False,
    intent: QueryIntent | None = None,
    enabled_channels: set[ChannelName] | None = None,
    channel_priority: dict[ChannelName, int] | None = None,
    ordered_channels: list[ChannelName] | None = None,
    bundles: list[ChannelBundle] | None = None,
    provenance: dict[SymbolRow, dict[str, float]] | None = None,
) -> str:
    """
    Render context output as structured JSON.

    Parameters
    ----------
    root : pathlib.Path
        Repository root used to format file paths.
    top_matches : list[repoindex.types.SymbolRow]
        Primary ranked symbols.
    doc_issues : list[tuple[str, str]]
        Related docstring issues.
    expanded : list[repoindex.types.SymbolRow]
        Secondary symbols collected by module expansion.
    unique_refs : list[repoindex.types.ReferenceRow]
        Cross-reference locations for selected symbols.
    confidence_map : dict[repoindex.types.SymbolRow, float] | None, optional
        Confidence values keyed by symbol.
    explain : bool, optional
        Whether explain metadata should be included.
    intent : repoindex.query.classifier.QueryIntent | None, optional
        Structured query classification.
    enabled_channels : set[repoindex.types.ChannelName] | None, optional
        Channels enabled for the query.
    channel_priority : dict[repoindex.types.ChannelName, int] | None, optional
        Channel priority mapping.
    ordered_channels : list[repoindex.types.ChannelName] | None, optional
        Ordered channel names.
    bundles : list[repoindex.types.ChannelBundle] | None, optional
        Raw channel results.
    provenance : dict[repoindex.types.SymbolRow, dict[str, float]] | None, optional
        Per-channel scores for merged symbols.

    Returns
    -------
    str
        JSON-encoded context payload.
    """
    status = "ok" if top_matches else "no_matches"
    _context_blocks: list[list[str]] = []
    _current_tokens = 0

    for s in top_matches[:ENRICHED_CONTEXT_LIMIT]:
        block = _format_enriched_symbol(root, s, {})
        block_tokens = _approx_token_count(block)

        if _current_tokens + block_tokens > MAX_TOKENS:
            break

        _context_blocks.append(block)
        _current_tokens += block_tokens

    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
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

        explain_block["environment"] = {
            "repoindex_version": __version__,
            "schema_version": SCHEMA_VERSION,
        }

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

            for channel_name, channel in bundles:
                entries: list[dict[str, object]] = []

                for score, symbol in channel[:5]:
                    symbol_type, module_name, name, _, lineno = symbol

                    entries.append(
                        {
                            "type": symbol_type,
                            "module": module_name,
                            "name": name,
                            "lineno": lineno,
                            "score": round(score, 2),
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
                    }
                )

            explain_block["merge"] = merge_entries

        result["explain"] = explain_block

    return json.dumps(result, indent=2)


def _render_context_prompt(
    root: Path,
    query: str,
    top_matches: list[SymbolRow],
    doc_issues: list[tuple[str, str]],
    expanded: list[SymbolRow],
    unique_refs: list[ReferenceRow],
) -> str:
    """
    Render context output in prompt form.

    Parameters
    ----------
    root : pathlib.Path
        Repository root used to relativize paths.
    query : str
        Original user query.
    top_matches : list[repoindex.types.SymbolRow]
        Primary ranked symbols.
    doc_issues : list[tuple[str, str]]
        Related docstring issues.
    expanded : list[repoindex.types.SymbolRow]
        Secondary symbols collected by module expansion.
    unique_refs : list[repoindex.types.ReferenceRow]
        Cross-reference locations for selected symbols.

    Returns
    -------
    str
        Prompt-formatted query context.
    """
    return _render_agent_prompt(
        root,
        query,
        top_matches,
        doc_issues,
        expanded,
        unique_refs,
    )


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

    Parameters
    ----------
    root : pathlib.Path
        Repository root used to relativize paths.
    query : str
        Original user query.
    top_matches : list[repoindex.types.SymbolRow]
        Primary ranked symbols.
    doc_issues : list[tuple[str, str]]
        Related docstring issues.
    expanded : list[repoindex.types.SymbolRow]
        Secondary symbols collected by module expansion.
    unique_refs : list[repoindex.types.ReferenceRow]
        Cross-reference locations for selected symbols.
    confidence_map : dict[repoindex.types.SymbolRow, float] | None, optional
        Confidence values keyed by symbol.
    as_json : bool, optional
        Whether to render JSON output.
    as_prompt : bool, optional
        Whether to render prompt output.
    explain : bool, optional
        Whether to include explain metadata.
    intent : repoindex.query.classifier.QueryIntent | None, optional
        Structured query classification.
    enabled_channels : set[repoindex.types.ChannelName] | None, optional
        Channels enabled for the query.
    channel_priority : dict[repoindex.types.ChannelName, int] | None, optional
        Channel priority mapping.
    ordered_channels : list[repoindex.types.ChannelName] | None, optional
        Ordered channel names.
    bundles : list[repoindex.types.ChannelBundle] | None, optional
        Raw channel results.
    provenance : dict[repoindex.types.SymbolRow, dict[str, float]] | None, optional
        Per-channel scores for merged symbols.

    Returns
    -------
    str
        Rendered context in plain-text, JSON, or prompt form.
    """
    if as_json:
        return _render_context_json(
            root,
            top_matches,
            doc_issues,
            expanded,
            unique_refs,
            confidence_map=confidence_map,
            explain=explain,
            intent=intent,
            enabled_channels=enabled_channels,
            channel_priority=channel_priority,
            ordered_channels=ordered_channels,
            bundles=bundles,
            provenance=provenance,
        )

    if as_prompt:
        return _render_context_prompt(
            root,
            query,
            top_matches,
            doc_issues,
            expanded,
            unique_refs,
        )

    lines: list[str] = []

    if explain:
        _append_explain_sections(
            lines,
            explain=explain,
            intent=intent,
            enabled_channels=enabled_channels,
            channel_priority=channel_priority,
            ordered_channels=ordered_channels,
            bundles=bundles,
            provenance=provenance,
            top_matches=top_matches,
        )

    _append_main_context_sections(
        lines,
        root,
        top_matches,
        doc_issues,
        expanded,
        unique_refs,
    )

    return "\n".join(lines)


def _append_explain_sections(
    lines: list[str],
    *,
    explain: bool,
    intent: QueryIntent | None,
    enabled_channels: set[ChannelName] | None,
    channel_priority: dict[ChannelName, int] | None,
    ordered_channels: list[ChannelName] | None,
    bundles: list[ChannelBundle] | None,
    provenance: dict[SymbolRow, dict[str, float]] | None,
    top_matches: list[SymbolRow],
) -> None:
    """
    Append explain-mode sections to the plain-text output buffer.

    Parameters
    ----------
    lines : list[str]
        Mutable output buffer.
    explain : bool
        Whether explain sections should be rendered.
    intent : repoindex.query.classifier.QueryIntent | None
        Structured query classification.
    enabled_channels : set[repoindex.types.ChannelName] | None
        Channels enabled for the query.
    channel_priority : dict[repoindex.types.ChannelName, int] | None
        Channel priority mapping.
    ordered_channels : list[repoindex.types.ChannelName] | None
        Ordered channel names.
    bundles : list[repoindex.types.ChannelBundle] | None
        Raw channel results.
    provenance : dict[repoindex.types.SymbolRow, dict[str, float]] | None
        Per-channel scores for merged symbols.
    top_matches : list[repoindex.types.SymbolRow]
        Primary merged symbols to explain.

    Returns
    -------
    None
        The explain sections are appended to ``lines`` in place.

    Notes
    -----
    Rendering is gated by ``explain``. When explain mode is disabled, the
    function leaves ``lines`` unchanged.
    """
    if explain:
        lines.append("=== EXPLAIN: ENVIRONMENT ===")
        lines.append(f"repoindex_version: {__version__}")
        lines.append(f"schema_version: {SCHEMA_VERSION}")
        lines.append("")
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

        for channel_name, channel in sorted(bundles, key=lambda item: item[0]):
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

            if not channel_scores:
                continue

            lines.append(label)

            sorted_scores = sorted(
                channel_scores.items(),
                key=lambda item: item[1],
                reverse=True,
            )

            for channel_name, score in sorted_scores:
                lines.append(f"  {channel_name}: {score:.2f}")

        lines.append("")


def _append_main_context_sections(
    lines: list[str],
    root: Path,
    top_matches: list[SymbolRow],
    doc_issues: list[tuple[str, str]],
    expanded: list[SymbolRow],
    unique_refs: list[ReferenceRow],
) -> None:
    """
    Append the main plain-text context sections to the output buffer.

    Parameters
    ----------
    lines : list[str]
        Mutable output buffer.
    root : pathlib.Path
        Repository root used to relativize paths.
    top_matches : list[repoindex.types.SymbolRow]
        Primary ranked symbols.
    doc_issues : list[tuple[str, str]]
        Related docstring issues.
    expanded : list[repoindex.types.SymbolRow]
        Secondary symbols collected by module expansion.
    unique_refs : list[repoindex.types.ReferenceRow]
        Cross-reference locations for selected symbols.

    Returns
    -------
    None
        The main context sections are appended to ``lines`` in place.

    Notes
    -----
    The function preserves the ranked order of ``top_matches`` and only emits
    enriched blocks for the configured leading subset.
    """
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
    for index, symbol in enumerate(top_matches[:ENRICHED_CONTEXT_LIMIT]):
        if index > 0:
            lines.append("")
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
    as_json : bool, optional
        Whether to emit the JSON representation.
    as_prompt : bool, optional
        Whether to emit the prompt-oriented representation.
    explain : bool, optional
        Whether to include retrieval diagnostics.

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

    Raises
    ------
    sqlite3.Error
        If the repository index cannot be opened or queried.
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
        conn,
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
