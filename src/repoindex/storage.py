"""Persistent storage helpers for the repoindex SQLite database."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from repoindex.schema import DDL, SCHEMA_VERSION


def _read_metadata_file(path: Path) -> dict[str, str]:
    """
    Load persisted index metadata from one JSON file.

    Parameters
    ----------
    path : pathlib.Path
        Metadata JSON path to decode.

    Returns
    -------
    dict[str, str]
        Parsed metadata values, or an empty mapping when the file does not
        exist or cannot be decoded.
    """
    if not path.exists():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _write_metadata_file(path: Path, data: dict[str, str]) -> None:
    """
    Persist index metadata atomically as JSON.

    Parameters
    ----------
    path : pathlib.Path
        Metadata JSON path to replace.
    data : dict[str, str]
        Metadata payload to serialize.

    Returns
    -------
    None
        The metadata file is replaced atomically in place.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


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
        "caller_file_id",
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
        "owner_file_id",
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


def _refresh_call_records_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``call_records`` table when an older schema is present.

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
    columns = conn.execute("PRAGMA table_info(call_records)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "file_id",
        "owner_module",
        "owner_name",
        "kind",
        "base",
        "target",
        "lineno",
        "col_offset",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_call_records_file")
    conn.execute("DROP INDEX IF EXISTS idx_call_records_owner")
    conn.execute("DROP TABLE IF EXISTS call_records")


def _refresh_callable_ref_records_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``callable_ref_records`` table when an older schema exists.

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
    columns = conn.execute("PRAGMA table_info(callable_ref_records)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "file_id",
        "owner_module",
        "owner_name",
        "kind",
        "ref_kind",
        "base",
        "target",
        "lineno",
        "col_offset",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_callable_ref_records_file")
    conn.execute("DROP INDEX IF EXISTS idx_callable_ref_records_owner")
    conn.execute("DROP TABLE IF EXISTS callable_ref_records")


def _refresh_docstring_issues_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``docstring_issues`` table when an older schema is present.

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
    columns = conn.execute("PRAGMA table_info(docstring_issues)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "id",
        "file_id",
        "function_id",
        "class_id",
        "module_id",
        "issue_type",
        "message",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_docstring_issues_file")
    conn.execute("DROP TABLE IF EXISTS docstring_issues")


def _refresh_imports_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``imports`` table when an older schema is present.

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
    columns = conn.execute("PRAGMA table_info(imports)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "id",
        "module_id",
        "name",
        "alias",
        "kind",
        "lineno",
    ]

    if current == expected:
        return

    conn.execute("DROP TABLE IF EXISTS imports")


def _refresh_files_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``files`` table when an older schema is present.

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
    columns = conn.execute("PRAGMA table_info(files)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "id",
        "path",
        "hash",
        "mtime",
        "size",
        "analyzer_name",
        "analyzer_version",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_files_path")
    conn.execute("DROP INDEX IF EXISTS idx_embeddings_object_backend_version")
    conn.execute("DROP INDEX IF EXISTS idx_symbol_name")
    conn.execute("DROP INDEX IF EXISTS idx_symbol_file")
    conn.execute("DROP INDEX IF EXISTS idx_docstring_issues_file")
    conn.execute("DROP INDEX IF EXISTS idx_call_edges_identity")
    conn.execute("DROP INDEX IF EXISTS idx_call_edges_caller")
    conn.execute("DROP INDEX IF EXISTS idx_call_edges_callee")
    conn.execute("DROP INDEX IF EXISTS idx_call_edges_resolved")
    conn.execute("DROP INDEX IF EXISTS idx_callable_refs_identity")
    conn.execute("DROP INDEX IF EXISTS idx_callable_refs_owner")
    conn.execute("DROP INDEX IF EXISTS idx_callable_refs_target")
    conn.execute("DROP INDEX IF EXISTS idx_callable_refs_resolved")
    conn.execute("DROP INDEX IF EXISTS idx_call_records_file")
    conn.execute("DROP INDEX IF EXISTS idx_call_records_owner")
    conn.execute("DROP INDEX IF EXISTS idx_callable_ref_records_file")
    conn.execute("DROP INDEX IF EXISTS idx_callable_ref_records_owner")
    conn.execute("DROP INDEX IF EXISTS idx_functions_name")
    conn.execute("DROP INDEX IF EXISTS idx_classes_name")
    conn.execute("DROP TABLE IF EXISTS embeddings")
    conn.execute("DROP TABLE IF EXISTS symbol_index")
    conn.execute("DROP TABLE IF EXISTS docstring_issues")
    conn.execute("DROP TABLE IF EXISTS callable_ref_records")
    conn.execute("DROP TABLE IF EXISTS call_records")
    conn.execute("DROP TABLE IF EXISTS callable_refs")
    conn.execute("DROP TABLE IF EXISTS call_edges")
    conn.execute("DROP TABLE IF EXISTS imports")
    conn.execute("DROP TABLE IF EXISTS functions")
    conn.execute("DROP TABLE IF EXISTS classes")
    conn.execute("DROP TABLE IF EXISTS modules")
    conn.execute("DROP TABLE IF EXISTS index_runtime")
    conn.execute("DROP TABLE IF EXISTS index_analyzers")
    conn.execute("DROP TABLE IF EXISTS files")


def _refresh_index_runtime_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``index_runtime`` table when an older schema is present.

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
    columns = conn.execute("PRAGMA table_info(index_runtime)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "singleton",
        "backend_name",
        "backend_version",
        "coverage_complete",
    ]

    if current == expected:
        return

    conn.execute("DROP TABLE IF EXISTS index_runtime")


def _refresh_index_analyzers_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``index_analyzers`` table when an older schema is present.

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
    columns = conn.execute("PRAGMA table_info(index_analyzers)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "name",
        "version",
        "discovery_globs",
    ]

    if current == expected:
        return

    conn.execute("DROP TABLE IF EXISTS index_analyzers")


def _refresh_symbol_index_schema(conn: sqlite3.Connection) -> None:
    """
    Recreate the ``symbol_index`` table when an older schema is present.

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
    columns = conn.execute("PRAGMA table_info(symbol_index)").fetchall()
    if not columns:
        return

    current = [str(row[1]) for row in columns]
    expected = [
        "id",
        "name",
        "stable_id",
        "type",
        "module_name",
        "file_id",
        "lineno",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_embeddings_object_backend_version")
    conn.execute("DROP TABLE IF EXISTS embeddings")
    conn.execute("DROP INDEX IF EXISTS idx_symbol_name")
    conn.execute("DROP INDEX IF EXISTS idx_symbol_file")
    conn.execute("DROP INDEX IF EXISTS idx_symbol_stable_id")
    conn.execute("DROP TABLE IF EXISTS symbol_index")


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
        "version",
        "content_hash",
        "dim",
        "vector",
    ]

    if current == expected:
        return

    conn.execute("DROP INDEX IF EXISTS idx_embeddings_object_backend")
    conn.execute("DROP INDEX IF EXISTS idx_embeddings_object_backend_version")
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
        _refresh_files_schema(conn)
        _refresh_call_edges_schema(conn)
        _refresh_callable_refs_schema(conn)
        _refresh_call_records_schema(conn)
        _refresh_callable_ref_records_schema(conn)
        _refresh_docstring_issues_schema(conn)
        _refresh_imports_schema(conn)
        _refresh_symbol_index_schema(conn)
        _refresh_embeddings_schema(conn)
        _refresh_index_runtime_schema(conn)
        _refresh_index_analyzers_schema(conn)
        for stmt in DDL:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()

    metadata_path = get_metadata_path(root)
    metadata = _read_metadata_file(metadata_path)
    metadata["schema_version"] = str(SCHEMA_VERSION)
    _write_metadata_file(metadata_path, metadata)
