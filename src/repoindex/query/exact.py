"""Exact lookup helpers backed by the repoindex SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.storage import get_db_path
from repoindex.types import SymbolRow

CallEdgeRow = tuple[str, str, str | None, str | None, int]
CallableRefRow = tuple[str, str, str | None, str | None, int]


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


def find_call_edges(
    root: Path,
    name: str,
    *,
    module: str | None = None,
    incoming: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[CallEdgeRow]:
    """
    Find exact call edges for a caller or callee logical name.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    name : str
        Exact logical caller or callee name to search for.
    module : str | None, optional
        Optional module qualifier used to restrict the result set.
    incoming : bool, optional
        When ``True``, return incoming edges for the callee; otherwise return
        outgoing edges for the caller.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[CallEdgeRow]
        Matching call-edge rows ordered deterministically.
    """
    owns_connection = conn is None
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    direction_column = "callee_name" if incoming else "caller_name"
    module_column = "callee_module" if incoming else "caller_module"

    query = f"""
        SELECT caller_module, caller_name, callee_module, callee_name, resolved
        FROM call_edges
        WHERE {direction_column} = ?
    """
    params: list[str] = [name]

    if module is not None:
        query += f" AND {module_column} = ?"
        params.append(module)

    query += """
        ORDER BY
            caller_module,
            caller_name,
            COALESCE(callee_module, ''),
            COALESCE(callee_name, ''),
            resolved
    """

    try:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [
            (
                str(caller_module),
                str(caller_name),
                None if callee_module is None else str(callee_module),
                None if callee_name is None else str(callee_name),
                int(resolved),
            )
            for caller_module, caller_name, callee_module, callee_name, resolved in rows
        ]
    finally:
        if owns_connection:
            conn.close()


def find_callable_refs(
    root: Path,
    name: str,
    *,
    module: str | None = None,
    incoming: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[CallableRefRow]:
    """
    Find exact callable-object references for an owner or referenced target.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    name : str
        Exact logical owner or referenced target name to search for.
    module : str | None, optional
        Optional module qualifier used to restrict the result set.
    incoming : bool, optional
        When ``True``, return incoming references for the target; otherwise
        return outgoing references for the owner.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[CallableRefRow]
        Matching callable-reference rows ordered deterministically.
    """
    owns_connection = conn is None
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    direction_column = "target_name" if incoming else "owner_name"
    module_column = "target_module" if incoming else "owner_module"

    query = f"""
        SELECT owner_module, owner_name, target_module, target_name, resolved
        FROM callable_refs
        WHERE {direction_column} = ?
    """
    params: list[str] = [name]

    if module is not None:
        query += f" AND {module_column} = ?"
        params.append(module)

    query += """
        ORDER BY
            owner_module,
            owner_name,
            COALESCE(target_module, ''),
            COALESCE(target_name, ''),
            resolved
    """

    try:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [
            (
                str(owner_module),
                str(owner_name),
                None if target_module is None else str(target_module),
                None if target_name is None else str(target_name),
                int(resolved),
            )
            for owner_module, owner_name, target_module, target_name, resolved in rows
        ]
    finally:
        if owns_connection:
            conn.close()
