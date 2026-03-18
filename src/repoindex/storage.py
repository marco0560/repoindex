from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from repoindex.schema import DDL, SCHEMA_VERSION


def get_repoindex_dir(root: Path) -> Path:
    return root / ".repoindex"


def get_db_path(root: Path) -> Path:
    return get_repoindex_dir(root) / "index.db"


def get_metadata_path(root: Path) -> Path:
    return get_repoindex_dir(root) / "metadata.json"


def init_db(root: Path) -> None:
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
