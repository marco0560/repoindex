# Tutorial

This walkthrough mirrors the installable example package in
`examples/plugins/repoindex_demo_analyzer`.

## 1. Create a package

```toml
[project]
name = "repoindex-demo-analyzer"
version = "0.1.0"
dependencies = ["repoindex"]

[project.entry-points."repoindex.analyzers"]
demo = "repoindex_demo_analyzer:build_analyzer"
```

## 2. Add the analyzer

```python
from pathlib import Path

from repoindex.contracts import LanguageAnalyzer
from repoindex.models import AnalysisResult, ModuleArtifact


class DemoAnalyzer:
    name = "demo"
    version = "1"
    discovery_globs = ("*.demo",)

    def supports_path(self, path: Path) -> bool:
        return path.suffix == ".demo"

    def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
        relative = path.with_suffix("").relative_to(root)
        module_name = ".".join(relative.parts)
        return AnalysisResult(
            source_path=path,
            module=ModuleArtifact(name=module_name, docstring=None, has_docstring=0),
            classes=(),
            functions=(),
            declarations=(),
            imports=(),
        )


def build_analyzer() -> LanguageAnalyzer:
    return DemoAnalyzer()
```

## 3. Install it

```bash
source .venv/bin/activate
pip install -e /path/to/repoindex-demo-analyzer
```

## 4. Verify discovery

```bash
repoindex plugins
```

Expected output should contain a loaded analyzer record for `demo`.

## 5. Index supported files

Once the analyzer is installed, any tracked `*.demo` file can participate in
the normal indexing run without patching `repoindex` itself.
