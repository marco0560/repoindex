from __future__ import annotations

from pathlib import Path

from repoindex.query.exact import find_symbol
from repoindex.storage import get_db_path


def context_for(root: Path, query: str) -> str:
    """
    Build a structured context block for a given query.

    The output is optimized for LLM consumption (Codex).
    """

    lines: list[str] = []

    # --- SYMBOL MATCHES ---
    matches = find_symbol(root, query)

    lines.append("=== SYMBOL MATCHES ===")

    if not matches:
        lines.append("No direct symbol matches found.")
    else:
        for typ, module, file_path, lineno in matches:
            lines.append(f"{typ}: {module}:{lineno} ({file_path})")

    # --- DOCSTRING ISSUES ---
    import sqlite3

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

    lines.append("\n=== RELATED DOCSTRING ISSUES ===")

    if not rows:
        lines.append("No related docstring issues.")
    else:
        for issue_type, message in rows:
            lines.append(f"{issue_type}: {message}")

    return "\n".join(lines)
