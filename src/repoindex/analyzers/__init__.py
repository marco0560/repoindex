"""Language analyzer implementations for repoindex."""

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
