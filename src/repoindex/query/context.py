from __future__ import annotations

from pathlib import Path

import sqlite3

from repoindex.query.exact import find_symbol
from repoindex.storage import get_db_path


def _symbols_in_module(root: Path, module: str) -> list[tuple[str, str, str, int]]:

    conn = sqlite3.connect(get_db_path(root))
    try:
        rows = conn.execute(
            """
            SELECT type, module_name, file_path, lineno
            FROM symbol_index
            WHERE module_name = ?
            LIMIT 20
            """,
            (module,),
        ).fetchall()
    finally:
        conn.close()

    return [(str(t), str(m), str(f), int(lineno)) for t, m, f, lineno in rows]


def context_for(root: Path, query: str) -> str:
    """
    Build a structured context block for a given query.

    The output is optimized for LLM consumption (Codex).
    """

    lines: list[str] = []

    # --- SYMBOL MATCHES ---
    matches = find_symbol(root, query)

    scored: list[tuple[int, tuple[str, str, str, int]]] = []

    for match in matches:
        typ, module, file_path, lineno = match

        score = 0

        if query == module:
            score += 3
        elif query in module:
            score += 2

        if query in typ:
            score += 1

        scored.append((score, match))

    scored.sort(reverse=True)
    top_matches: list[tuple[str, str, str, int]] = [m for _, m in scored[:10]]

    expanded: list[tuple[str, str, str, int]] = []

    seen_modules: set[str] = set()

    for typ, module, file_path, lineno in top_matches:
        if module in seen_modules:
            continue

        seen_modules.add(module)

        symbols = _symbols_in_module(root, module)

        for s in symbols:
            if s not in expanded:
                expanded.append(s)

    expanded = expanded[:20]

    # --- DOCSTRING ISSUES ---

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

    # --- BUILD RELATED SYMBOLS FROM ISSUES ---
    related_symbols: list[tuple[str, str, str, int]] = []

    for issue_type, message in rows:
        parts = message.split(":")[0].split()

        if len(parts) >= 2:
            symbol_name = parts[-1]
            matches = find_symbol(root, symbol_name)
            related_symbols.extend(matches)

    # --- MERGE SYMBOLS ---
    for m in related_symbols:
        if m not in top_matches:
            top_matches.append(m)

    top_matches = top_matches[:10]

    # --- OUTPUT: TOP MATCHES ---
    lines.append("=== TOP MATCHES ===")

    if not top_matches:
        lines.append("No direct symbol matches found.")
    else:
        for typ, module, file_path, lineno in top_matches:
            lines.append(f"{typ}: {module}:{lineno} ({file_path})")

    # --- OUTPUT: SUGGESTED CONTEXT ---
    lines.append("\n=== SUGGESTED CONTEXT ===")

    for typ, module, file_path, lineno in top_matches[:5]:
        lines.append(f"{typ} in {module}")
        lines.append(f"  File: {file_path}")
        lines.append(f"  Line: {lineno}")

    lines.append("\n=== MODULE EXPANSION ===")

    if not expanded:
        lines.append("No module expansion available.")
    else:
        for typ, module, file_path, lineno in expanded:
            lines.append(f"{typ}: {module}:{lineno}")

    # --- OUTPUT: DOCSTRING ISSUES ---
    lines.append("\n=== RELATED DOCSTRING ISSUES ===")

    if not rows:
        lines.append("No related docstring issues.")
    else:
        for issue_type, message in rows:
            lines.append(f"{issue_type}: {message}")

    return "\n".join(lines)