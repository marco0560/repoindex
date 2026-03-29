"""Tests for ADR-004 Phase 3 contract and normalization models."""

from __future__ import annotations

import importlib
import json
import sqlite3
import subprocess
from pathlib import Path

from pytest import MonkeyPatch

from repoindex.analyzers import CAnalyzer, PythonAnalyzer
from repoindex.contracts import IndexBackend, LanguageAnalyzer
from repoindex.indexer import (
    SQLiteIndexBackend,
    _collect_indexed_file_analyses,
    _select_language_analyzer,
    index_repo,
)
from repoindex.models import (
    AnalysisResult,
    CallSite,
    FileMetadataSnapshot,
    ModuleArtifact,
)
from repoindex.normalization import analysis_result_from_parsed
from repoindex.parser_ast import parse_file
from repoindex.registry import (
    _instantiate_language_analyzers,
    active_index_backend,
    active_language_analyzers,
    missing_language_analyzer_hint,
)
from repoindex.scanner import (
    discovery_file_globs,
    iter_canonical_project_files,
    iter_project_files,
)
from repoindex.storage import get_db_path


class _FakeAnalyzer:
    """Small analyzer stub used to validate the protocol surface."""

    name = "fake-python"
    version = "1"
    discovery_globs: tuple[str, ...] = ("*.py",)

    def supports_path(self, path: Path) -> bool:
        """
        Report support for Python files.

        Parameters
        ----------
        path : pathlib.Path
            Candidate source path.

        Returns
        -------
        bool
            ``True`` for Python files.
        """
        return path.suffix == ".py"

    def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
        """
        Analyze one file through the existing Python parser path.

        Parameters
        ----------
        path : pathlib.Path
            Source file to analyze.
        root : pathlib.Path
            Repository root used for module resolution.

        Returns
        -------
        repoindex.models.AnalysisResult
            Normalized analysis result for the file.
        """
        parsed = parse_file(path, root)
        return analysis_result_from_parsed(path, parsed)


class _FakeBackend:
    """Small backend stub used to validate the protocol surface."""

    name = "fake-backend"
    version = "1"

    def initialize(self, root: Path) -> None:
        """
        Perform no-op initialization for the fake backend.

        Parameters
        ----------
        root : pathlib.Path
            Repository root.

        Returns
        -------
        None
            This fake backend keeps no state.
        """
        return None

    def load_existing_file_hashes(self, root: Path) -> dict[str, str]:
        """
        Return an empty file-hash mapping.

        Parameters
        ----------
        root : pathlib.Path
            Repository root.

        Returns
        -------
        dict[str, str]
            Empty mapping for protocol validation.
        """
        return {}

    def delete_paths(self, root: Path, *, paths: list[str]) -> None:
        """
        Perform no-op path deletion for the fake backend.

        Parameters
        ----------
        root : pathlib.Path
            Repository root.
        paths : list[str]
            Paths that would be deleted.

        Returns
        -------
        None
            This fake backend keeps no state.
        """
        return None

    def persist_analysis(
        self,
        root: Path,
        *,
        file_metadata: FileMetadataSnapshot,
        analysis: AnalysisResult,
    ) -> int:
        """
        Count normalized functions as a stand-in for persisted artifacts.

        Parameters
        ----------
        root : pathlib.Path
            Repository root.
        file_metadata : repoindex.models.FileMetadataSnapshot
            Stable file metadata snapshot.
        analysis : repoindex.models.AnalysisResult
            Normalized analyzer output.

        Returns
        -------
        int
            Number of normalized functions and methods.
        """
        return len(analysis.iter_functions())

    def count_reusable_embeddings(self, root: Path, *, paths: list[str]) -> int:
        """
        Count supplied paths as a stand-in reusable-artifact metric.

        Parameters
        ----------
        root : pathlib.Path
            Repository root.
        paths : list[str]
            Reusable paths.

        Returns
        -------
        int
            Number of reusable paths.
        """
        return len(paths)

    def rebuild_derived_indexes(self, root: Path) -> None:
        """
        Perform no-op derived-index rebuilding.

        Parameters
        ----------
        root : pathlib.Path
            Repository root.

        Returns
        -------
        None
            This fake backend keeps no state.
        """
        return None

    def find_include_edges(
        self,
        root: Path,
        name: str,
        *,
        module: str | None = None,
        incoming: bool = False,
        prefix: str | None = None,
        conn: object | None = None,
    ) -> list[tuple[str, str, str, int]]:
        """
        Return no include edges for protocol validation.

        Parameters
        ----------
        root : pathlib.Path
            Repository root.
        name : str
            Owner module or include target.
        module : str | None, optional
            Optional module filter.
        incoming : bool, optional
            Whether incoming include edges would be requested.
        prefix : str | None, optional
            Optional owner-file prefix filter.
        conn : object | None, optional
            Optional backend connection.

        Returns
        -------
        list[tuple[str, str, str, int]]
            Empty include-edge rows for protocol validation.
        """
        del root, name, module, incoming, prefix, conn
        return []


def test_analysis_result_from_parsed_normalizes_python_artifacts(
    tmp_path: Path,
) -> None:
    """
    Normalize current parser output into the ADR-004 artifact model.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts normalized module, function, method, call, and import
        artifacts.
    """
    module = tmp_path / "pkg" / "sample.py"
    module.parent.mkdir()
    module.write_text(
        '"""Fixture module."""\n'
        "\n"
        "from pkg.helpers import helper as external\n"
        "\n"
        "@pytest.fixture\n"
        "def sample_fixture():\n"
        '    """Build the sample payload."""\n'
        "    return 1\n"
        "\n"
        "def top_level(value):\n"
        '    """Return the direct helper call."""\n'
        "    return external(value)\n"
        "\n"
        "class Demo:\n"
        "    def method(self):\n"
        '        """Return the imported helper."""\n'
        "        assert external is not None\n"
        '        return {"helper": external}\n',
        encoding="utf-8",
    )

    parsed = parse_file(module, tmp_path)
    result = analysis_result_from_parsed(module, parsed)

    assert result.module.name == "pkg.sample"
    assert tuple(import_row.name for import_row in result.imports) == (
        "pkg.helpers.helper",
    )
    assert tuple(function.name for function in result.functions) == (
        "sample_fixture",
        "top_level",
    )
    assert result.functions[0].decorators == ("pytest.fixture",)
    assert result.functions[0].has_asserts == 0
    assert tuple(class_row.name for class_row in result.classes) == ("Demo",)
    assert result.classes[0].methods[0].logical_name(class_name="Demo") == "Demo.method"
    assert result.classes[0].methods[0].has_asserts == 1
    assert tuple(call.target for call in result.iter_call_sites()) == ("external",)
    assert tuple(ref.target for ref in result.iter_callable_references()) == (
        "external",
    )


def test_language_analyzer_and_index_backend_protocols_are_runtime_checkable() -> None:
    """
    Ensure the Phase 3 protocol types accept conforming implementations.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts runtime protocol compatibility for analyzer and
        backend stubs.
    """
    assert isinstance(PythonAnalyzer(), LanguageAnalyzer)
    assert isinstance(CAnalyzer(), LanguageAnalyzer)
    assert isinstance(_FakeAnalyzer(), LanguageAnalyzer)
    assert isinstance(_FakeBackend(), IndexBackend)


def test_active_phase_8_registries_expose_default_backend_and_analyzers() -> None:
    """
    Keep the Phase 8 registry defaults explicit and runtime-checkable.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts the default backend and analyzer registry instances.
    """
    backend = active_index_backend()
    analyzers = active_language_analyzers()

    assert isinstance(backend, IndexBackend)
    assert isinstance(backend, SQLiteIndexBackend)
    assert [analyzer.name for analyzer in analyzers] == ["python", "c"]


def test_active_language_analyzers_skip_optional_c_when_dependencies_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    """
    Skip the optional C analyzer when its extra dependencies are unavailable.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest fixture used to intercept module imports.

    Returns
    -------
    None
        The test asserts the registry keeps Python active and omits C.
    """
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> object:
        if name == "repoindex.analyzers.c":
            raise ModuleNotFoundError(
                "No module named 'tree_sitter_c'",
                name="tree_sitter_c",
            )
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    analyzers = active_language_analyzers()

    assert [analyzer.name for analyzer in analyzers] == ["python"]


def test_select_language_analyzer_reports_optional_extra_hint(
    monkeypatch: MonkeyPatch,
) -> None:
    """
    Report the optional extra when a C-family file has no available analyzer.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest fixture used to intercept module imports.

    Returns
    -------
    None
        The test asserts the failure message includes the C extra hint.
    """
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> object:
        if name == "repoindex.analyzers.c":
            raise ModuleNotFoundError(
                "No module named 'tree_sitter_c'",
                name="tree_sitter_c",
            )
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    analyzers = active_language_analyzers()

    try:
        _select_language_analyzer(Path("native/sample.c"), analyzers)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ValueError for missing optional C analyzer")

    assert "No language analyzer registered for path: native/sample.c" in message
    assert "repoindex[c]" in message
    assert missing_language_analyzer_hint(Path("native/sample.c")) is not None


def test_c_analyzer_normalizes_functions_and_includes(tmp_path: Path) -> None:
    """
    Validate the Phase 9 C analyzer proof against normalized artifacts.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts deterministic module, include, and function output.
    """
    source = tmp_path / "pkg" / "sample.c"
    source.parent.mkdir()
    source.write_text(
        '#include "pkg/sample.h"\n'
        "#include <stdio.h>\n"
        "\n"
        "static int helper(int value) {\n"
        "    return value;\n"
        "}\n"
        "\n"
        "int public_api(void) {\n"
        "    return helper(1);\n"
        "}\n",
        encoding="utf-8",
    )

    result = CAnalyzer().analyze_file(source, tmp_path)

    assert result.module.name == "pkg.sample"
    assert tuple(import_row.name for import_row in result.imports) == (
        "pkg/sample.h",
        "stdio.h",
    )
    assert tuple(import_row.kind for import_row in result.imports) == (
        "include_local",
        "include_system",
    )
    assert tuple(function.name for function in result.functions) == (
        "helper",
        "public_api",
    )
    assert result.functions[0].parameters == ("value",)
    assert result.functions[0].is_public == 0
    assert result.functions[1].parameters == ()
    assert result.functions[1].is_public == 1


def test_c_analyzer_extracts_top_level_declarations(tmp_path: Path) -> None:
    """
    Normalize top-level C type declarations into module-level symbols.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts deterministic struct, enum, and typedef extraction.
    """
    source = tmp_path / "native" / "types.h"
    source.parent.mkdir()
    source.write_text(
        "/* Node representation for graph edges. */\n"
        "typedef struct Node { int value; } Node;\n"
        "\n"
        "// Available palette values.\n"
        "enum Color { RED, BLUE };\n"
        "\n"
        "struct Pair { int left; int right; };\n"
        "\n"
        "/* Stable integer alias. */\n"
        "typedef unsigned long size_t;\n",
        encoding="utf-8",
    )

    result = CAnalyzer().analyze_file(source, tmp_path)

    assert [
        (declaration.kind, declaration.name, declaration.lineno)
        for declaration in result.declarations
    ] == [
        ("struct", "Node", 2),
        ("typedef", "Node", 2),
        ("enum", "Color", 5),
        ("struct", "Pair", 7),
        ("typedef", "size_t", 10),
    ]
    assert result.declarations[0].signature == "struct Node { int value; }"
    assert (
        result.declarations[1].signature == "typedef struct Node { int value; } Node;"
    )
    assert result.declarations[0].docstring == "Node representation for graph edges."
    assert result.declarations[1].docstring == "Node representation for graph edges."
    assert result.declarations[2].docstring == "Available palette values."
    assert result.declarations[3].docstring is None
    assert result.declarations[4].docstring == "Stable integer alias."


def test_discovery_file_globs_follow_analyzer_registration_order() -> None:
    """
    Derive deterministic scanner globs from analyzer metadata.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts analyzer-registration order is preserved while
        duplicate globs are removed.
    """
    analyzers = [PythonAnalyzer(), CAnalyzer(), _FakeAnalyzer()]

    assert discovery_file_globs(analyzers) == ("*.py", "*.c", "*.h")


def test_iter_project_files_uses_analyzer_declared_globs(tmp_path: Path) -> None:
    """
    Discover files through analyzer-declared globs outside Git repositories.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts scanner discovery is not limited to the former
        hard-coded core glob tuple.
    """

    class _DemoAnalyzer:
        name = "demo"
        version = "1"
        discovery_globs: tuple[str, ...] = ("*.demo",)

        def supports_path(self, path: Path) -> bool:
            return path.suffix == ".demo"

        def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
            del root
            return AnalysisResult(
                source_path=path,
                module=ModuleArtifact(
                    name=path.stem,
                    docstring=None,
                    has_docstring=0,
                ),
                classes=(),
                functions=(),
                declarations=(),
                imports=(),
            )

    demo_file = tmp_path / "src" / "sample.demo"
    ignored_file = tmp_path / "src" / "sample.py"
    demo_file.parent.mkdir()
    demo_file.write_text("demo\n", encoding="utf-8")
    ignored_file.write_text("print('ignored')\n", encoding="utf-8")

    discovered = list(iter_project_files(tmp_path, analyzers=[_DemoAnalyzer()]))

    assert discovered == [demo_file]


def test_iter_project_files_uses_analyzer_globs_with_git(tmp_path: Path) -> None:
    """
    Discover tracked files through analyzer-declared globs inside Git repos.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts Git-backed discovery follows analyzer metadata.
    """

    class _DemoAnalyzer:
        name = "demo"
        version = "1"
        discovery_globs: tuple[str, ...] = ("*.demo",)

        def supports_path(self, path: Path) -> bool:
            return path.suffix == ".demo"

        def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
            del root
            return AnalysisResult(
                source_path=path,
                module=ModuleArtifact(
                    name=path.stem,
                    docstring=None,
                    has_docstring=0,
                ),
                classes=(),
                functions=(),
                declarations=(),
                imports=(),
            )

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    demo_file = tmp_path / "src" / "sample.demo"
    other_file = tmp_path / "src" / "sample.py"
    demo_file.parent.mkdir()
    demo_file.write_text("demo\n", encoding="utf-8")
    other_file.write_text("print('ignored')\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "src/sample.demo", "src/sample.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    discovered = list(iter_project_files(tmp_path, analyzers=[_DemoAnalyzer()]))

    assert discovered == [demo_file]


def test_iter_canonical_project_files_uses_git_tracked_directories(
    tmp_path: Path,
) -> None:
    """
    Discover tracked files under canonical directories through Git.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts canonical-directory discovery does not depend on the
        active analyzer set.
    """
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    src_file = tmp_path / "src" / "main.rs"
    test_file = tmp_path / "tests" / "test_main.py"
    docs_file = tmp_path / "docs" / "notes.md"
    src_file.parent.mkdir()
    test_file.parent.mkdir()
    docs_file.parent.mkdir()
    src_file.write_text("fn main() {}\n", encoding="utf-8")
    test_file.write_text("def test_demo():\n    pass\n", encoding="utf-8")
    docs_file.write_text("# ignored\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "src/main.rs", "tests/test_main.py", "docs/notes.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    discovered = list(iter_canonical_project_files(tmp_path))

    assert discovered == [src_file, test_file]


def test_c_analyzer_extracts_calls_returns_and_module_comment(tmp_path: Path) -> None:
    """
    Preserve Phase 11 C semantic-parity artifacts within the current model.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts call extraction, return detection, and module comment
        capture for C sources.
    """
    source = tmp_path / "native" / "flow.c"
    source.parent.mkdir()
    source.write_text(
        "/* Vector reduction helpers. */\n"
        "\n"
        "static int helper(int value) {\n"
        "    return obj->normalize(value);\n"
        "}\n"
        "\n"
        "int public_api(int input) {\n"
        '    trace("value");\n'
        "    return helper(input);\n"
        "}\n",
        encoding="utf-8",
    )

    result = CAnalyzer().analyze_file(source, tmp_path)

    assert result.module.docstring == "Vector reduction helpers."
    assert result.module.has_docstring == 1
    assert tuple(function.name for function in result.functions) == (
        "helper",
        "public_api",
    )
    assert result.functions[0].returns_value == 1
    assert result.functions[0].calls == (
        CallSite(
            kind="attribute",
            target="normalize",
            lineno=4,
            col_offset=16,
            base="obj",
        ),
    )
    assert result.functions[1].returns_value == 1
    assert tuple(call.target for call in result.functions[1].calls) == (
        "trace",
        "helper",
    )


def test_c_analyzer_ignores_macro_blocks_misparsed_as_functions(
    tmp_path: Path,
) -> None:
    """
    Skip malformed macro blocks that tree-sitter exposes as functions.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts only real function definitions are normalized.
    """
    source = tmp_path / "native" / "macro_noise.c"
    source.parent.mkdir()
    source.write_text(
        "#define CTL_PROTO(x) x\n"
        "#define MUTEX_STATS_CTL_PROTO_GEN(n) \\\n"
        "CTL_PROTO(stats_##n##_num_ops) \\\n"
        "CTL_PROTO(stats_##n##_num_wait)\n"
        "\n"
        "typedef int ctl_named_node_t;\n"
        "#define OP(mtx) MUTEX_STATS_CTL_PROTO_GEN(mutexes_##mtx)\n"
        "static const ctl_named_node_t stats_node[] = {\n"
        "    OP(background_thread),\n"
        "};\n"
        "#undef OP\n"
        "\n"
        "int real(void) {\n"
        "    return 1;\n"
        "}\n",
        encoding="utf-8",
    )

    result = CAnalyzer().analyze_file(source, tmp_path)

    assert tuple(function.name for function in result.functions) == ("real",)
    assert result.functions[0].signature == "int real(void)"


def test_c_import_kinds_persist_through_sqlite_backend(tmp_path: Path) -> None:
    """
    Persist C include-kind metadata through the current SQLite backend.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts stored local and system include kinds.
    """
    source = tmp_path / "native" / "sample.c"
    source.parent.mkdir()
    source.write_text(
        '#include "native/sample.h"\n'
        "#include <stdio.h>\n"
        "\n"
        "int demo(void) {\n"
        "    return 1;\n"
        "}\n",
        encoding="utf-8",
    )

    backend = SQLiteIndexBackend()
    backend.initialize(tmp_path)
    analysis = CAnalyzer().analyze_file(source, tmp_path)
    snapshot = FileMetadataSnapshot(
        path=source,
        sha256="abc123",
        mtime=1.0,
        size=source.stat().st_size,
    )
    backend.persist_analysis(
        tmp_path,
        file_metadata=snapshot,
        analysis=analysis,
    )

    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        rows = conn.execute("""
            SELECT i.name, i.kind
            FROM imports i
            JOIN modules m
              ON i.module_id = m.id
            ORDER BY i.lineno, i.name
            """).fetchall()
    finally:
        conn.close()

    assert rows == [
        ("native/sample.h", "include_local"),
        ("stdio.h", "include_system"),
    ]


def test_c_declarations_persist_as_exact_symbols(tmp_path: Path) -> None:
    """
    Persist C declaration artifacts into the existing exact-symbol index.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts exact symbol lookup for persisted C declarations.
    """
    source = tmp_path / "native" / "types.h"
    source.parent.mkdir()
    source.write_text(
        "typedef struct Node { int value; } Node;\n"
        "enum Color { RED, BLUE };\n"
        "struct Pair { int left; int right; };\n"
        "typedef unsigned long size_t;\n",
        encoding="utf-8",
    )

    backend = SQLiteIndexBackend()
    backend.initialize(tmp_path)
    analysis = CAnalyzer().analyze_file(source, tmp_path)
    snapshot = FileMetadataSnapshot(
        path=source,
        sha256="abc123",
        mtime=1.0,
        size=source.stat().st_size,
    )
    backend.persist_analysis(
        tmp_path,
        file_metadata=snapshot,
        analysis=analysis,
    )

    assert backend.find_symbol(tmp_path, "Node") == [
        ("struct", "native.types", "Node", str(source), 1),
        ("typedef", "native.types", "Node", str(source), 1),
    ]
    assert backend.find_symbol(tmp_path, "Color") == [
        ("enum", "native.types", "Color", str(source), 2),
    ]
    assert backend.find_symbol(tmp_path, "size_t") == [
        ("typedef", "native.types", "size_t", str(source), 4),
    ]


def test_c_declaration_comments_contribute_to_embedding_candidates(
    tmp_path: Path,
) -> None:
    """
    Include leading declaration comments in C semantic symbol retrieval.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts embedding retrieval can match declaration comments.
    """
    source = tmp_path / "native" / "types.h"
    source.parent.mkdir()
    source.write_text(
        "/* Palette lookup for UI themes. */\n" "enum Color { RED, BLUE };\n",
        encoding="utf-8",
    )

    backend = SQLiteIndexBackend()
    backend.initialize(tmp_path)
    analysis = CAnalyzer().analyze_file(source, tmp_path)
    snapshot = FileMetadataSnapshot(
        path=source,
        sha256="abc123",
        mtime=1.0,
        size=source.stat().st_size,
    )
    backend.persist_analysis(
        tmp_path,
        file_metadata=snapshot,
        analysis=analysis,
    )

    results = backend.embedding_candidates(
        tmp_path,
        "palette lookup themes",
        limit=5,
        min_score=0.0,
    )

    assert results
    assert results[0][1] == ("enum", "native.types", "Color", str(source), 2)


def test_active_index_backend_rejects_unknown_configured_backend(
    monkeypatch: MonkeyPatch,
) -> None:
    """
    Reject unsupported backend configuration deterministically.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest fixture used to set process-local environment variables.

    Returns
    -------
    None
        The test asserts an informative failure for unsupported backend names.
    """
    monkeypatch.setenv("REPOINDEX_INDEX_BACKEND", "unknown")

    try:
        active_index_backend()
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ValueError for unsupported backend")

    assert "Unsupported repoindex backend 'unknown'" in message
    assert "sqlite" in message


def test_instantiating_language_analyzers_requires_a_non_empty_registry() -> None:
    """
    Reject empty analyzer registries with an explicit deterministic error.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts the registry failure path used by Phase 8.
    """
    try:
        _instantiate_language_analyzers(())
    except ValueError as exc:
        assert str(exc) == "No language analyzers are registered for repoindex"
    else:
        raise AssertionError("expected ValueError for empty analyzer registry")


def test_sqlite_index_backend_persists_and_deletes_normalized_analysis(
    tmp_path: Path,
) -> None:
    """
    Exercise the concrete SQLite backend through the Phase 3 contract surface.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts normalized persistence, reusable embedding counting,
        and deletion through `SQLiteIndexBackend`.
    """
    module = tmp_path / "pkg" / "sample.py"
    module.parent.mkdir()
    module.write_text(
        "def demo(value):\n"
        '    """Return the supplied value."""\n'
        "    return value\n",
        encoding="utf-8",
    )

    backend = SQLiteIndexBackend()
    backend.initialize(tmp_path)

    parsed = parse_file(module, tmp_path)
    analysis = analysis_result_from_parsed(module, parsed)
    snapshot = FileMetadataSnapshot(
        path=module,
        sha256="abc123",
        mtime=1.0,
        size=module.stat().st_size,
    )

    assert isinstance(backend, IndexBackend)
    written = backend.persist_analysis(
        tmp_path,
        file_metadata=snapshot,
        analysis=analysis,
    )
    backend.rebuild_derived_indexes(tmp_path)

    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        file_hashes = backend.load_existing_file_hashes(tmp_path, conn=conn)
        symbol_rows = conn.execute(
            "SELECT name, type FROM symbol_index ORDER BY name, type"
        ).fetchall()
    finally:
        conn.close()

    assert written == 2
    assert file_hashes == {str(module): "abc123"}
    assert symbol_rows == [
        ("demo", "function"),
        ("pkg.sample", "module"),
    ]
    assert backend.find_symbol(tmp_path, "demo") == [
        (
            "function",
            "pkg.sample",
            "demo",
            str(module),
            1,
        )
    ]
    assert backend.embedding_inventory(tmp_path) == [("hash-v1", "1", 128, 2)]
    assert backend.embedding_candidates(
        tmp_path,
        "return supplied value",
        limit=5,
        min_score=0.0,
    )
    assert backend.count_reusable_embeddings(tmp_path, paths=[str(module)]) == 2

    backend.delete_paths(tmp_path, paths=[str(module)])
    assert backend.load_existing_file_hashes(tmp_path) == {}


def test_select_language_analyzer_uses_first_supporting_analyzer(
    tmp_path: Path,
) -> None:
    """
    Preserve deterministic analyzer routing order in the Phase 5 orchestrator.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts first-match routing for a supported path.
    """

    class _RejectingAnalyzer:
        name = "reject"
        version = "1"
        discovery_globs: tuple[str, ...] = ("*.py",)

        def supports_path(self, path: Path) -> bool:
            return False

        def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
            raise AssertionError("should not be called")

    analyzer = _select_language_analyzer(
        tmp_path / "sample.py",
        [_RejectingAnalyzer(), _FakeAnalyzer()],
    )

    assert analyzer is not None
    assert analyzer.name == "fake-python"


def test_collect_indexed_file_analyses_routes_paths_to_analyzers(
    tmp_path: Path,
) -> None:
    """
    Collect normalized analyses through the Phase 5 analyzer-routing helper.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts snapshot conversion and analyzer-produced artifacts.
    """
    module = tmp_path / "pkg" / "sample.py"
    module.parent.mkdir()
    module.write_text(
        "def demo():\n" '    """Return a constant."""\n' "    return 1\n",
        encoding="utf-8",
    )

    rows, failures, collected_warnings = _collect_indexed_file_analyses(
        tmp_path,
        [str(module)],
        {
            str(module): {
                "path": str(module),
                "hash": "abc123",
                "mtime": 1.0,
                "size": module.stat().st_size,
            }
        },
        [_FakeAnalyzer()],
    )

    assert failures == []
    assert collected_warnings == []
    assert len(rows) == 1
    path, snapshot, analysis = rows[0]
    assert path == module
    assert snapshot == FileMetadataSnapshot(
        path=module,
        sha256="abc123",
        mtime=1.0,
        size=module.stat().st_size,
        analyzer_name="fake-python",
        analyzer_version="1",
    )
    assert analysis.module.name == "pkg.sample"


def test_sqlite_backend_persists_file_analyzer_ownership(tmp_path: Path) -> None:
    """
    Persist analyzer ownership metadata on file rows.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts persisted file rows record analyzer name and version.
    """
    backend = SQLiteIndexBackend()
    backend.initialize(tmp_path)
    module = tmp_path / "pkg" / "sample.py"
    module.parent.mkdir()
    module.write_text(
        "def demo():\n" '    """Return a constant."""\n' "    return 1\n",
        encoding="utf-8",
    )
    snapshot = FileMetadataSnapshot(
        path=module,
        sha256="hash-v1",
        mtime=1.0,
        size=module.stat().st_size,
        analyzer_name="python",
        analyzer_version="1",
    )
    analysis = PythonAnalyzer().analyze_file(module, tmp_path)

    backend.persist_analysis(
        tmp_path,
        file_metadata=snapshot,
        analysis=analysis,
    )

    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        row = conn.execute(
            """
            SELECT analyzer_name, analyzer_version
            FROM files
            WHERE path = ?
            """,
            (str(module),),
        ).fetchone()
    finally:
        conn.close()

    assert row == ("python", "1")


def test_sqlite_backend_persists_runtime_inventory(tmp_path: Path) -> None:
    """
    Persist runtime backend and analyzer inventory for one index run.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts backend runtime metadata and analyzer inventory are
        stored in the SQLite database.
    """
    module = tmp_path / "pkg" / "sample.py"
    module.parent.mkdir()
    module.write_text(
        "def demo():\n" '    """Return a constant."""\n' "    return 1\n",
        encoding="utf-8",
    )

    index_repo(tmp_path)

    backend = SQLiteIndexBackend()
    assert backend.load_runtime_inventory(tmp_path) == ("sqlite", "10", 1)
    assert backend.load_analyzer_inventory(tmp_path) == [
        (
            analyzer.name,
            analyzer.version,
            json.dumps(tuple(analyzer.discovery_globs)),
        )
        for analyzer in sorted(active_language_analyzers(), key=lambda item: item.name)
    ]
