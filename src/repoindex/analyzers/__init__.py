"""Language analyzer implementations for repoindex.

Responsibilities
----------------
- Re-export analyzer classes and helpers such as Python and C analyzer implementations.
- Provide aggregator utilities used by the indexer and registry layers to enumerate analyzers.
- Surface analyzer metadata so the registry can compute discovery globs and optional dependencies.

Design principles
-----------------
The package stays lightweight and only re-exports language-specific analyzer classes.

Architectural role
------------------
This module belongs to the **language analyzer registration layer** of ADR-004.
"""

import importlib

from repoindex.analyzers.python import PythonAnalyzer

__all__ = ["PythonAnalyzer"]

try:
    CAnalyzer = importlib.import_module("repoindex.analyzers.c").CAnalyzer
except ModuleNotFoundError as exc:
    if exc.name not in {"tree_sitter", "tree_sitter_c"}:
        raise
else:
    __all__.append("CAnalyzer")

try:
    BashAnalyzer = importlib.import_module("repoindex.analyzers.bash").BashAnalyzer
except ModuleNotFoundError as exc:
    if exc.name not in {"tree_sitter", "tree_sitter_bash"}:
        raise
else:
    __all__.append("BashAnalyzer")
