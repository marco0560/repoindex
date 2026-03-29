"""Example analyzer plugin for repoindex."""

from pathlib import Path
from typing import cast

from repoindex.contracts import LanguageAnalyzer
from repoindex.models import AnalysisResult, ModuleArtifact


class DemoAnalyzer:
    """
    Minimal analyzer for ``*.demo`` files.

    Parameters
    ----------
    None
    """

    name = "demo"
    version = "1"
    discovery_globs: tuple[str, ...] = ("*.demo",)

    def supports_path(self, path: Path) -> bool:
        """
        Return whether this plugin accepts the supplied path.

        Parameters
        ----------
        path : pathlib.Path
            Candidate repository path.

        Returns
        -------
        bool
            ``True`` when the path uses the ``.demo`` suffix.
        """
        return path.suffix == ".demo"

    def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
        """
        Emit a minimal module artifact for one ``*.demo`` file.

        Parameters
        ----------
        path : pathlib.Path
            Source file accepted by the demo analyzer.
        root : pathlib.Path
            Repository root used to derive the module name.

        Returns
        -------
        repoindex.models.AnalysisResult
            Minimal normalized module analysis for the input file.
        """
        relative_path = path.relative_to(root)
        module_name = ".".join(relative_path.with_suffix("").parts)
        return AnalysisResult(
            source_path=path,
            module=ModuleArtifact(
                name=module_name,
                docstring=None,
                has_docstring=0,
            ),
            classes=(),
            functions=(),
            declarations=(),
            imports=(),
        )


def build_analyzer() -> LanguageAnalyzer:
    """
    Build the example analyzer plugin instance.

    Parameters
    ----------
    None

    Returns
    -------
    repoindex.contracts.LanguageAnalyzer
        Example analyzer instance cast to the public plugin contract.
    """
    return cast("LanguageAnalyzer", DemoAnalyzer())
