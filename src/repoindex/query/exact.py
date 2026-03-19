from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.storage import get_db_path

SymbolRow = tuple[str, str, str, str, int]


def find_symbol(root: Path, name: str) -> list[SymbolRow]:
    conn = sqlite3.connect(get_db_path(root))
    try:
        rows = conn.execute(
            """
            SELECT type, module_name, name, file_path, lineno
            FROM symbol_index
            WHERE name = ?
            ORDER BY type, module_name, file_path, lineno
            """,
            (name,),
        ).fetchall()

        return [
            (str(t), str(m), str(n), str(f), int(lineno)) for t, m, n, f, lineno in rows
        ]
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
