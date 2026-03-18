from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.storage import get_db_path


def find_symbol(root: Path, name: str) -> list[tuple[str, str, str, int]]:
    conn = sqlite3.connect(get_db_path(root))
    try:
        rows = conn.execute(
            """
            SELECT type, module_name, file_path, lineno
            FROM symbol_index
            WHERE name = ?
            ORDER BY type, module_name, file_path, lineno
            """,
            (name,),
        ).fetchall()
        return [(str(t), str(m), str(f), int(lineno)) for t, m, f, lineno in rows]
    finally:
        conn.close()


def docstring_issues(root: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(get_db_path(root))
    try:
        rows = conn.execute("""
            SELECT issue_type, message
            FROM docstring_issues
            ORDER BY issue_type, message
            """).fetchall()
        return [(str(t), str(m)) for t, m in rows]
    finally:
        conn.close()
