from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path
from typing import cast

from repoindex.query.exact import find_symbol
from repoindex.storage import get_db_path

SymbolRow = tuple[str, str, str, str, int]
ReferenceRow = tuple[str, int]
CodeContext = tuple[str | None, str | None, list[str]]


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


def _snippet_from_lines(source_lines: list[str], lineno: int, limit: int = 5) -> list[str]:
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

    if hasattr(node, "decorator_list") and node.decorator_list:
        try:
            start = min(d.lineno for d in node.decorator_list) - 1
        except Exception:
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
            cast(ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module, node),
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
                line for i, line in enumerate(snippet)
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

def _iter_python_files(root: Path) -> list[Path]:
    """
    Return Python files tracked by git.

    Falls back to filesystem scan if git is unavailable.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )

        return [root / line.strip() for line in result.stdout.splitlines() if line.strip()]

    except Exception:
        # fallback: filesystem scan
        return list(root.rglob("*.py"))


def _find_references(
    root: Path,
    name: str,
    project_files: list[Path],
) -> list[ReferenceRow]:
    """
    Find references to a symbol name across Python files.

    This is a simple string-based search:
    - scans all `.py` files under root
    - returns (file_path, lineno)
    - excludes hidden directories (e.g., .venv, .git)
    - skips import statements
    - limits results to avoid explosion
    """

    results: list[ReferenceRow] = []

    try:
        for path in project_files:

            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            try:
                rel = path.relative_to(root)
                file_path = str(rel)
            except Exception:
                file_path = str(path)

            for lineno, line in enumerate(lines, start=1):

                stripped = line.strip()

                # --- FILTER: skip imports ---
                if stripped.startswith(("import ", "from ")):
                    continue

                # simple containment check
                if name in line:
                    results.append((file_path, lineno))

                    # hard cap (global)
                    if len(results) >= 100:
                        return results

    except Exception:
        return []

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
        return f"{head} ({file_path})"
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

    lines.append(f"  File: {file_path}")
    lines.append(f"  Line: {lineno}")

    if snippet:
        lines.append("  Snippet:")
        for line in snippet:
            lines.append(f"    {line}")

    if docstring:
        lines.append("  Docstring:")
        for line in docstring.splitlines():
            lines.append(f"    {line}")

    return lines


def context_for(root: Path, query: str) -> str:
    """
    Build a structured context block for a given query.

    The output is optimized for LLM consumption.
    """

    lines: list[str] = []

    matches = find_symbol(root, query)

    project_files = _iter_python_files(root)

    all_candidates: list[SymbolRow]
    if matches:
        all_candidates = matches
    else:
        conn = sqlite3.connect(get_db_path(root))
        try:
            rows = conn.execute("""
                SELECT type, module_name, name, file_path, lineno
                FROM symbol_index
                LIMIT 200
                """).fetchall()
        finally:
            conn.close()

        all_candidates = [
            (str(t), str(m), str(n), str(f), int(lin)) for t, m, n, f, lin in rows
        ]

    scored: list[tuple[int, SymbolRow]] = []

    for candidate in all_candidates:
        score = _score_match(list(_tokenize(query)), candidate)
        if score > 0:
            scored.append((score, candidate))

    scored.sort(reverse=True)
    top_matches: list[SymbolRow] = [match for _, match in scored[:10]]

    conn = sqlite3.connect(get_db_path(root))
    try:
        rows = conn.execute(
            """
            SELECT issue_type, message
            FROM docstring_issues
            WHERE message LIKE ?
            LIMIT 20
            """,
            (f"%{query}%",),
        ).fetchall()
    finally:
        conn.close()

    related_symbols: list[SymbolRow] = []

    for _, message in rows:
        parts = message.split(":")[0].split()
        if len(parts) >= 2:
            symbol_name = parts[-1]
            related_symbols.extend(find_symbol(root, symbol_name))

    for match in related_symbols:
        if match not in top_matches:
            top_matches.append(match)

    top_matches = top_matches[:10]

    expanded: list[SymbolRow] = []
    seen_modules: set[str] = set()

    for _, module_name, _, _, _ in top_matches:
        if module_name in seen_modules:
            continue

        seen_modules.add(module_name)

        for symbol in _symbols_in_module(root, module_name):
            if symbol not in expanded:
                expanded.append(symbol)

    expanded = expanded[:20]

    symbol_names = {name for _, _, name, _, _ in top_matches if name}

    references: list[ReferenceRow] = []
    top_files = {file_path for _, _, _, file_path, _ in top_matches}

    for name in symbol_names:
        for file_path, lineno in _find_references(root, name, project_files):
            if file_path not in top_files:
                references.append((file_path, lineno))

    seen_refs: set[ReferenceRow] = set()
    unique_refs: list[ReferenceRow] = []

    for ref in references:
        if ref not in seen_refs:
            seen_refs.add(ref)
            unique_refs.append(ref)

    unique_refs = unique_refs[:20]

    lines.append("=== TOP MATCHES ===")
    if not top_matches:
        lines.append("No direct symbol matches found.")
    else:
        for symbol in top_matches:
            lines.append(_format_symbol(symbol, include_path=True))

    lines.append("\n=== RELATED DOCSTRING ISSUES ===")
    if not rows:
        lines.append("No related docstring issues.")
    else:
        for issue_type, message in rows:
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
            lines.append(f"{file_path}:{lineno}")

    return "\n".join(lines)
