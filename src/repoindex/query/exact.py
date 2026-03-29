"""Exact lookup helpers backed by the active repoindex index backend."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.registry import active_index_backend
from repoindex.types import IncludeEdgeRow, SymbolRow

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
    backend = active_index_backend()
    return backend.find_symbol(root, name, prefix=prefix, conn=conn)


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
    backend = active_index_backend()
    return backend.docstring_issues(root, prefix=prefix, conn=conn)


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
    backend = active_index_backend()
    return backend.find_call_edges(
        root,
        name,
        module=module,
        incoming=incoming,
        prefix=prefix,
        conn=conn,
    )


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
    backend = active_index_backend()
    return backend.find_callable_refs(
        root,
        name,
        module=module,
        incoming=incoming,
        prefix=prefix,
        conn=conn,
    )


def find_include_edges(
    root: Path,
    name: str,
    *,
    module: str | None = None,
    incoming: bool = False,
    prefix: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[IncludeEdgeRow]:
    """
    Find exact include-like edges for an owner module or included target.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    name : str
        Exact owner module name or include target path to search for.
    module : str | None, optional
        Optional owner-module qualifier used to restrict incoming results.
    incoming : bool, optional
        When ``True``, return incoming include edges for the included target;
        otherwise return outgoing include edges for the owner module.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict owner files.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    list[repoindex.types.IncludeEdgeRow]
        Matching include-edge rows ordered deterministically as
        ``(owner_module, target_name, kind, lineno)`` tuples.
    """
    backend = active_index_backend()
    return backend.find_include_edges(
        root,
        name,
        module=module,
        incoming=incoming,
        prefix=prefix,
        conn=conn,
    )


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
    backend = active_index_backend()
    return backend.find_logical_symbols(
        root,
        module_name,
        logical_name,
        prefix=prefix,
        conn=conn,
    )


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
    backend = active_index_backend()
    return backend.logical_symbol_name(root, symbol, conn=conn)


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
    backend = active_index_backend()
    return backend.embedding_inventory(root, conn=conn)
