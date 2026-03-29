"""Python language analyzer for ADR-004."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from repoindex.models import AnalysisResult

from repoindex.normalization import analysis_result_from_parsed
from repoindex.parser_ast import parse_file


class PythonAnalyzer:
    """
    Concrete Python analyzer for repository indexing.

    Parameters
    ----------
    None

    Notes
    -----
    This analyzer owns Python-specific parsing and normalization only. It does
    not own backend persistence or indexing policy.
    """

    name = "python"
    version = "1"
    discovery_globs: tuple[str, ...] = ("*.py",)

    def supports_path(self, path: Path) -> bool:
        """
        Decide whether the analyzer accepts a source path.

        Parameters
        ----------
        path : pathlib.Path
            Candidate repository file.

        Returns
        -------
        bool
            ``True`` when the file is a Python source file.
        """
        return path.suffix == ".py"

    def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
        """
        Analyze one Python source file into normalized artifacts.

        Parameters
        ----------
        path : pathlib.Path
            Python source file to analyze.
        root : pathlib.Path
            Repository root used for module-name derivation.

        Returns
        -------
        repoindex.models.AnalysisResult
            Normalized analysis result for the file.
        """
        return analysis_result_from_parsed(path, parse_file(path, root))
