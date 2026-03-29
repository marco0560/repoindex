"""Example analyzer plugin for repoindex."""

from pathlib import Path
from typing import cast

from repoindex.contracts import LanguageAnalyzer
from repoindex.models import AnalysisResult, ModuleArtifact


class DemoAnalyzer:
    """Minimal analyzer for ``*.demo`` files."""

    name = "demo"
    version = "1"
    discovery_globs: tuple[str, ...] = ("*.demo",)

    def supports_path(self, path: Path) -> bool:
        """Return whether this plugin accepts the supplied path."""
        return path.suffix == ".demo"

    def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
        """Emit a minimal module artifact for one ``*.demo`` file."""
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
    """Build the example analyzer plugin instance."""
    return cast(LanguageAnalyzer, DemoAnalyzer())
