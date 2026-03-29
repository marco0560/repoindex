"""Example backend plugin for repoindex."""

from typing import cast

from repoindex.contracts import IndexBackend
from repoindex.indexer import SQLiteIndexBackend


class DemoBackend(SQLiteIndexBackend):
    """Minimal third-party backend that reuses SQLite storage."""

    name = "demo-backend"


def build_backend() -> IndexBackend:
    """Build the example backend plugin instance."""
    return cast(IndexBackend, DemoBackend())
