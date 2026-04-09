"""Compatibility shim for the extracted first-party Python analyzer package.

Responsibilities
----------------
- Preserve historical imports from `repoindex.analyzers.python`.
- Redirect callers to the extracted `repoindex_analyzer_python` package.
- Raise a deterministic operator-facing error when the package is absent.

Design principles
-----------------
The shim stays intentionally narrow so the extracted package owns the real
implementation logic.

Architectural role
------------------
This module belongs to the **compatibility layer** of the Phase 2 package
boundary migration.
"""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from repoindex_analyzer_python import PythonAnalyzer as _PythonAnalyzerType

__all__ = ["PythonAnalyzer"]


def _load_monorepo_package() -> None:
    """
    Add the extracted Python analyzer package source tree to ``sys.path`` locally.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The monorepo package source directory is prepended when present.
    """
    package_src = (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "repoindex-analyzer-python"
        / "src"
    )
    if package_src.is_dir():
        package_src_text = str(package_src)
        if package_src_text not in sys.path:
            sys.path.insert(0, package_src_text)


try:
    python_module = import_module("repoindex_analyzer_python")
except ModuleNotFoundError as exc:
    if exc.name != "repoindex_analyzer_python":
        raise
    _load_monorepo_package()
    try:
        python_module = import_module("repoindex_analyzer_python")
    except ModuleNotFoundError as second_exc:
        if second_exc.name != "repoindex_analyzer_python":
            raise
        msg = (
            "The first-party Python analyzer now lives in the separate "
            "`repoindex-analyzer-python` package. Install that package to keep "
            "using `repoindex.analyzers.python` compatibility imports."
        )
        raise ModuleNotFoundError(msg, name=second_exc.name) from second_exc

PythonAnalyzer = cast("type[_PythonAnalyzerType]", python_module.PythonAnalyzer)
