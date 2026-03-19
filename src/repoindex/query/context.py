from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from repoindex.query.exact import find_symbol
from repoindex.storage import get_db_path

SymbolRow = tuple[str, str, str, str, int]
ReferenceRow = tuple[str, int]


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


def _find_references(root: Path, symbol_name: str) -> list[ReferenceRow]:
    """
    Find files referencing a symbol name using symbol_index entries.

    This is a deterministic, lightweight approximation of cross-module usage.
    """

    conn = sqlite3.connect(get_db_path(root))
    try:
        rows = conn.execute(
            """
            SELECT file_path, lineno
            FROM symbol_index
            WHERE name LIKE ?
            LIMIT 20
            """,
            (f"%{symbol_name}%",),
        ).fetchall()
    finally:
        conn.close()

    return [(str(file_path), int(lineno)) for file_path, lineno in rows]


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


def _score_match(query: str, match: SymbolRow) -> int:
    symbol_type, module_name, name, file_path, lineno = match
    del file_path, lineno

    score = 0

    query_l = query.lower()
    module_l = module_name.lower()
    name_l = name.lower()
    type_l = symbol_type.lower()

    query_tokens = _tokenize(query_l)
    module_tokens = _tokenize(module_l)
    name_tokens = _tokenize(name_l)

    if query_l in name_l:
        score += 10
    if query_l in module_l:
        score += 4
    if query_l in type_l:
        score += 1

    score += len(query_tokens & name_tokens) * 3
    score += len(query_tokens & module_tokens)

    for qt in query_tokens:
        for nt in name_tokens:
            if qt in nt or nt in qt:
                score += 2
                continue
            if qt[:5] == nt[:5]:
                score += 2

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


def context_for(root: Path, query: str) -> str:
    """
    Build a structured context block for a given query.

    The output is optimized for LLM consumption.
    """

    lines: list[str] = []

    matches = find_symbol(root, query)

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
        score = _score_match(query, candidate)
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
        for file_path, lineno in _find_references(root, name):
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
    for symbol_type, module_name, name, file_path, lineno in top_matches[:5]:
        if symbol_type == "module":
            lines.append(f"{symbol_type} {module_name}")
        else:
            lines.append(f"{symbol_type} {name} in {module_name}")
        lines.append(f"  File: {file_path}")
        lines.append(f"  Line: {lineno}")

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
