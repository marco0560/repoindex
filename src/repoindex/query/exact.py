"""Exact lookup helpers backed by the repoindex SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.storage import get_db_path
from repoindex.types import SymbolRow

CallEdgeRow = tuple[str, str, str | None, str | None, int]
CallableRefRow = tuple[str, str, str | None, str | None, int]
EmbeddingInventoryRow = tuple[str, str, int, int]


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


def find_logical_symbols(
    root: Path,
    module_name: str,
    logical_name: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[SymbolRow]:
    """
    Resolve a logical callable name back to indexed symbol rows.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    module_name : str
        Dotted module that owns the logical symbol.
    logical_name : str
        Logical symbol identity such as ``helper`` or ``Class.method``.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[repoindex.types.SymbolRow]
        Matching indexed symbol rows ordered deterministically.
    """
    owns_connection = conn is None
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    try:
        if "." in logical_name:
            class_name, method_name = logical_name.rsplit(".", 1)
            rows = conn.execute(
                """
                SELECT
                    s.type,
                    s.module_name,
                    s.name,
                    s.file_path,
                    s.lineno
                FROM functions f
                JOIN classes c
                  ON f.class_id = c.id
                JOIN modules m
                  ON f.module_id = m.id
                JOIN symbol_index s
                  ON s.type = 'method'
                 AND s.module_name = m.name
                 AND s.name = f.name
                 AND s.lineno = f.lineno
                WHERE m.name = ? AND c.name = ? AND f.name = ?
                ORDER BY s.file_path, s.lineno, s.name
                """,
                (module_name, class_name, method_name),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT type, module_name, name, file_path, lineno
                FROM symbol_index
                WHERE module_name = ?
                  AND (name = ? OR (type = 'module' AND module_name = ?))
                ORDER BY type, module_name, file_path, lineno
                """,
                (module_name, logical_name, logical_name),
            ).fetchall()

        return [
            (str(t), str(m), str(n), str(f), int(lineno)) for t, m, n, f, lineno in rows
        ]
    finally:
        if owns_connection:
            conn.close()


def logical_symbol_name(
    root: Path,
    symbol: SymbolRow,
    *,
    conn: sqlite3.Connection | None = None,
) -> str:
    """
    Return the logical graph identity for one indexed symbol row.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    symbol : repoindex.types.SymbolRow
        Indexed symbol row whose logical identity should be resolved.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    str
        Logical symbol identity used by call edges and callable references.
    """
    symbol_type, module_name, name, _file_path, lineno = symbol
    if symbol_type != "method":
        return module_name if symbol_type == "module" else name

    owns_connection = conn is None
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    try:
        row = conn.execute(
            """
            SELECT c.name
            FROM functions f
            JOIN classes c
              ON f.class_id = c.id
            JOIN modules m
              ON f.module_id = m.id
            WHERE m.name = ? AND f.name = ? AND f.lineno = ?
            ORDER BY c.name
            LIMIT 1
            """,
            (module_name, name, lineno),
        ).fetchone()
        if row is None:
            return name
        return f"{str(row[0])}.{name}"
    finally:
        if owns_connection:
            conn.close()


def embedding_inventory(
    root: Path,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[EmbeddingInventoryRow]:
    """
    Return stored embedding inventory grouped by backend metadata.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[EmbeddingInventoryRow]
        Rows as ``(backend, version, dim, count)`` ordered deterministically.
    """
    owns_connection = conn is None
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    try:
        rows = conn.execute("""
            SELECT backend, version, dim, COUNT(*)
            FROM embeddings
            GROUP BY backend, version, dim
            ORDER BY backend, version, dim
            """).fetchall()
        return [
            (str(backend), str(version), int(dim), int(count))
            for backend, version, dim, count in rows
        ]
    finally:
        if owns_connection:
            conn.close()
