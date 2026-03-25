"""Persistent storage helpers for the repoindex SQLite database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from repoindex.schema import DDL, SCHEMA_VERSION


def _refresh_call_edges_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``call_edges`` table when an older schema is present.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection to migrate in place.

    Returns
    -------
    None
        The table is replaced only when its columns do not match the current
        schema definition.
    """
    columns = conn.execute("PRAGMA table_info(call_edges)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "caller_module",
        "caller_name",
        "callee_module",
        "callee_name",
        "resolved",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_call_edges_identity")
    conn.execute("DROP INDEX IF EXISTS idx_call_edges_caller")
    conn.execute("DROP INDEX IF EXISTS idx_call_edges_callee")
    conn.execute("DROP INDEX IF EXISTS idx_call_edges_resolved")
    conn.execute("DROP TABLE IF EXISTS call_edges")


def _refresh_callable_refs_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``callable_refs`` table when an older schema is present.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection to migrate in place.

    Returns
    -------
    None
        The table is replaced only when its columns do not match the current
        schema definition.
    """
    columns = conn.execute("PRAGMA table_info(callable_refs)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "owner_module",
        "owner_name",
        "target_module",
        "target_name",
        "resolved",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_callable_refs_identity")
    conn.execute("DROP INDEX IF EXISTS idx_callable_refs_owner")
    conn.execute("DROP INDEX IF EXISTS idx_callable_refs_target")
    conn.execute("DROP INDEX IF EXISTS idx_callable_refs_resolved")
    conn.execute("DROP TABLE IF EXISTS callable_refs")


def _refresh_embeddings_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``embeddings`` table when an older schema is present.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection to migrate in place.

    Returns
    -------
    None
        The table is replaced only when its columns do not match the current
        schema definition.
    """
    columns = conn.execute("PRAGMA table_info(embeddings)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "id",
        "object_type",
        "object_id",
        "backend",
        "dim",
        "vector",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_embeddings_object_backend")
    conn.execute("DROP TABLE IF EXISTS embeddings")


def get_repoindex_dir(root: Path) -> Path:
    """
    Return the repository-local storage directory.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    pathlib.Path
        Path to the ``.repoindex`` directory under ``root``.
    """
    return root / ".repoindex"


def get_db_path(root: Path) -> Path:
    """
    Return the SQLite database path for a repository.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    pathlib.Path
        Path to the ``index.db`` file under ``.repoindex``.
    """
    return get_repoindex_dir(root) / "index.db"


def get_metadata_path(root: Path) -> Path:
    """
    Return the metadata JSON path for a repository.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    pathlib.Path
        Path to the ``metadata.json`` file under ``.repoindex``.
    """
    return get_repoindex_dir(root) / "metadata.json"


def init_db(root: Path) -> None:
    """
    Create or refresh the repoindex database schema.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose ``.repoindex`` directory should be initialized.

    Returns
    -------
    None
        The schema and metadata files are created or refreshed under
        ``root / ".repoindex"``.
    """
    repo_dir = get_repoindex_dir(root)
    repo_dir.mkdir(exist_ok=True)

    db_path = get_db_path(root)

    conn = sqlite3.connect(db_path)
    try:
        _refresh_call_edges_schema(conn)
        _refresh_callable_refs_schema(conn)
        _refresh_embeddings_schema(conn)
        for stmt in DDL:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()

    metadata = {
        "schema_version": str(SCHEMA_VERSION),
    }

    with open(get_metadata_path(root), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
