"""Exact lookup helpers backed by the repoindex SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.prefix import normalize_prefix, prefix_clause
from repoindex.storage import get_db_path
from repoindex.types import SymbolRow

CallEdgeRow = tuple[str, str, str | None, str | None, int]
CallableRefRow = tuple[str, str, str | None, str | None, int]
EmbeddingInventoryRow = tuple[str, str, int, int]


def find_symbol(
    root: Path,
    name: str,
    *,
    prefix: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[SymbolRow]:
    """
    Find exact symbol-name matches in the index.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    name : str
        Exact symbol name to search for.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict symbol files.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[SymbolRow]
        Matching symbol rows ordered deterministically.
    """
    owns_connection = conn is None
    normalized_prefix = normalize_prefix(root, prefix)

    if conn is None:
        conn = sqlite3.connect(get_db_path(root))
    try:
        prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
        rows = conn.execute(
            f"""
            SELECT s.type, s.module_name, s.name, f.path, s.lineno
            FROM symbol_index s
            JOIN files f
              ON s.file_id = f.id
            WHERE s.name = ?
            {prefix_sql}
            ORDER BY s.type, s.module_name, f.path, s.lineno
            """,
            (name, *prefix_params),
        ).fetchall()

        return [
            (str(t), str(m), str(n), str(f), int(lineno)) for t, m, n, f, lineno in rows
        ]
    finally:
        if owns_connection:
            conn.close()


def docstring_issues(
    root: Path,
    *,
    prefix: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[tuple[str, str]]:
    """
    Return indexed docstring validation issues.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict issue ownership.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[tuple[str, str]]
        Issue rows as ``(issue_type, message)`` tuples.
    """
    owns_connection = conn is None
    normalized_prefix = normalize_prefix(root, prefix)
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))
    try:
        prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
        rows = conn.execute(
            f"""
            SELECT di.issue_type, di.message
            FROM docstring_issues di
            JOIN files f
              ON di.file_id = f.id
            WHERE 1 = 1
            {prefix_sql}
            ORDER BY di.issue_type, di.message
            """,
            tuple(prefix_params),
        ).fetchall()

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
    prefix: str | None = None,
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
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict caller files.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[CallEdgeRow]
        Matching call-edge rows ordered deterministically.
    """
    owns_connection = conn is None
    normalized_prefix = normalize_prefix(root, prefix)
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    direction_column = "callee_name" if incoming else "caller_name"
    module_column = "callee_module" if incoming else "caller_module"
    prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")

    query = f"""
        SELECT
            ce.caller_module,
            ce.caller_name,
            ce.callee_module,
            ce.callee_name,
            ce.resolved
        FROM call_edges ce
        JOIN files f
          ON ce.caller_file_id = f.id
        WHERE {direction_column} = ?
        {prefix_sql}
    """
    params: list[str] = [name, *prefix_params]

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
    prefix: str | None = None,
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
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict owner files.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[CallableRefRow]
        Matching callable-reference rows ordered deterministically.
    """
    owns_connection = conn is None
    normalized_prefix = normalize_prefix(root, prefix)
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    direction_column = "target_name" if incoming else "owner_name"
    module_column = "target_module" if incoming else "owner_module"
    prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")

    query = f"""
        SELECT
            cr.owner_module,
            cr.owner_name,
            cr.target_module,
            cr.target_name,
            cr.resolved
        FROM callable_refs cr
        JOIN files f
          ON cr.owner_file_id = f.id
        WHERE {direction_column} = ?
        {prefix_sql}
    """
    params: list[str] = [name, *prefix_params]

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
    prefix: str | None = None,
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
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict symbol files.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[repoindex.types.SymbolRow]
        Matching indexed symbol rows ordered deterministically.
    """
    owns_connection = conn is None
    normalized_prefix = normalize_prefix(root, prefix)
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    try:
        if "." in logical_name:
            class_name, method_name = logical_name.rsplit(".", 1)
            prefix_sql, prefix_params = prefix_clause(normalized_prefix, "fp.path")
            rows = conn.execute(
                f"""
                SELECT
                    s.type,
                    s.module_name,
                    s.name,
                    fp.path,
                    s.lineno
                FROM functions fn
                JOIN classes c
                  ON fn.class_id = c.id
                JOIN modules m
                  ON fn.module_id = m.id
                JOIN symbol_index s
                  ON s.type = 'method'
                 AND s.module_name = m.name
                 AND s.name = fn.name
                 AND s.lineno = fn.lineno
                JOIN files fp
                  ON s.file_id = fp.id
                WHERE m.name = ? AND c.name = ? AND fn.name = ?
                {prefix_sql}
                ORDER BY fp.path, s.lineno, s.name
                """,
                (module_name, class_name, method_name, *prefix_params),
            ).fetchall()
        else:
            prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
            rows = conn.execute(
                f"""
                SELECT s.type, s.module_name, s.name, f.path, s.lineno
                FROM symbol_index s
                JOIN files f
                  ON s.file_id = f.id
                WHERE s.module_name = ?
                  AND (s.name = ? OR (s.type = 'module' AND s.module_name = ?))
                {prefix_sql}
                ORDER BY s.type, s.module_name, f.path, s.lineno
                """,
                (module_name, logical_name, logical_name, *prefix_params),
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
