"""Persistent storage helpers for the repoindex SQLite database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from repoindex.schema import DDL, SCHEMA_VERSION


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
    """
    repo_dir = get_repoindex_dir(root)
    repo_dir.mkdir(exist_ok=True)

    db_path = get_db_path(root)

    conn = sqlite3.connect(db_path)
    try:
        for stmt in DDL:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()

    metadata = {
        "schema_version": SCHEMA_VERSION,
    }

    with open(get_metadata_path(root), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
