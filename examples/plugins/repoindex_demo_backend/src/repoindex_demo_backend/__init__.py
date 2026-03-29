"""Example backend plugin for repoindex."""

from typing import cast

from repoindex.contracts import IndexBackend
from repoindex.indexer import SQLiteIndexBackend


class DemoBackend(SQLiteIndexBackend):
    """Minimal third-party backend that reuses SQLite storage."""

    name = "demo-backend"


def build_backend() -> IndexBackend:
    """
    Build the example backend plugin instance.

    Parameters
    ----------
    None

    Returns
    -------
    repoindex.contracts.IndexBackend
        Example backend instance cast to the public plugin contract.
    """
    return cast("IndexBackend", DemoBackend())
