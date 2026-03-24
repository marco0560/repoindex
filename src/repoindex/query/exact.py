"""Exact lookup helpers backed by the repoindex SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.storage import get_db_path
from repoindex.types import SymbolRow


def find_symbol(
    root: Path, name: str, conn: sqlite3.Connection | None = None
) -> list[SymbolRow]:
    """
    Find exact symbol-name matches in the index.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    name : str
        Exact symbol name to search for.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[SymbolRow]
        Matching symbol rows ordered deterministically.
    """
    owns_connection = conn is None

    if conn is None:
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
        if owns_connection:
            conn.close()


def docstring_issues(
    root: Path, conn: sqlite3.Connection | None = None
) -> list[tuple[str, str]]:
    """
    Return indexed docstring validation issues.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[tuple[str, str]]
        Issue rows as ``(issue_type, message)`` tuples.
    """
    owns_connection = conn is None
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))
    try:
        rows = conn.execute("""
            SELECT issue_type, message
            FROM docstring_issues
            ORDER BY issue_type, message
            """).fetchall()

        return [(str(t), str(m)) for t, m in rows]
    finally:
        if owns_connection:
            conn.close()
