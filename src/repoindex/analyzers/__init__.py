"""Language analyzer exports for repoindex.

Responsibilities
----------------
- Re-export the built-in Python and JSON analyzers.
- Preserve transitional imports for extracted first-party analyzers when their
  packages are installed.
- Keep analyzer imports lightweight for registry and test callers.

Design principles
-----------------
The package stays lightweight and avoids owning optional first-party analyzer
implementations directly.

Architectural role
------------------
This module belongs to the **language analyzer registration layer** of ADR-004.
"""

import importlib

from repoindex.analyzers.json import JsonAnalyzer
from repoindex.analyzers.python import PythonAnalyzer

__all__ = ["PythonAnalyzer", "JsonAnalyzer"]

try:
    c_module = importlib.import_module("repoindex.analyzers.c")
except ModuleNotFoundError as exc:
    if exc.name not in {"repoindex_analyzer_c", "tree_sitter_c"}:
        raise
else:
    CAnalyzer = c_module.CAnalyzer
    __all__.append("CAnalyzer")

try:
    bash_module = importlib.import_module("repoindex.analyzers.bash")
except ModuleNotFoundError as exc:
    if exc.name not in {"repoindex_analyzer_bash", "tree_sitter_bash"}:
        raise
else:
    BashAnalyzer = bash_module.BashAnalyzer
    __all__.append("BashAnalyzer")
