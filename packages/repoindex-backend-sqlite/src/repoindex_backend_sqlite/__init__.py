"""First-party SQLite backend plugin package for repoindex.

Responsibilities
----------------
- Publish the canonical SQLite backend through the `repoindex.backends` entry-point group.
- Expose the concrete first-party SQLite backend class from the package boundary.
- Keep the package-facing backend factory explicit and deterministic.

Design principles
-----------------
The package owns distribution and the concrete runtime class while the
repository continues to preserve historical imports during the Phase 2
transition.

Architectural role
------------------
This module belongs to the **first-party backend plugin layer** introduced by
ADR-012.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from repoindex.indexer import SQLiteIndexBackend as _CompatSQLiteIndexBackend

if TYPE_CHECKING:
    from repoindex.contracts import IndexBackend

__all__ = ["SQLiteIndexBackend", "build_backend"]


class SQLiteIndexBackend(_CompatSQLiteIndexBackend):
    """
    First-party SQLite backend class exposed from the package boundary.

    Parameters
    ----------
    None

    Notes
    -----
    The current implementation still reuses the compatibility behavior exposed
    by ``repoindex.indexer`` until the remaining Phase 2 extraction work moves
    the lower-level helper logic fully behind the package boundary.
    """


def build_backend() -> IndexBackend:
    """
    Build the first-party SQLite backend plugin instance.

    Parameters
    ----------
    None

    Returns
    -------
    repoindex.contracts.IndexBackend
        Active SQLite backend instance cast to the public backend contract.
    """
    return cast("IndexBackend", SQLiteIndexBackend())
