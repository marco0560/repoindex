"""Compatibility shim for the extracted first-party C analyzer package.

Responsibilities
----------------
- Preserve historical imports from `repoindex.analyzers.c`.
- Redirect callers to the extracted `repoindex_analyzer_c` package.
- Raise a deterministic operator-facing error when the package is absent.

Design principles
-----------------
The shim stays intentionally narrow so the extracted package owns the real
implementation logic.

Architectural role
------------------
This module belongs to the **compatibility layer** of the Phase 1 package
boundary migration.
"""

from __future__ import annotations

__all__ = ["CAnalyzer", "_disambiguate_function_stable_ids"]

try:
    from repoindex_analyzer_c import CAnalyzer, _disambiguate_function_stable_ids
except ModuleNotFoundError as exc:
    if exc.name != "repoindex_analyzer_c":
        raise
    msg = (
        "The first-party C analyzer now lives in the separate "
        "`repoindex-analyzer-c` package. Install that package to keep using "
        "`repoindex.analyzers.c` compatibility imports."
    )
    raise ModuleNotFoundError(msg, name=exc.name) from exc
