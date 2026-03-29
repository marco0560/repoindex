"""Tests for third-party plugin discovery and reporting."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import repoindex.registry as registry
from repoindex.cli import main
from repoindex.contracts import IndexBackend, LanguageAnalyzer
from repoindex.indexer import SQLiteIndexBackend
from repoindex.models import AnalysisResult, ModuleArtifact

if TYPE_CHECKING:
    import pytest


@dataclass(frozen=True)
class _FakeDistribution:
    """Minimal distribution record for fake entry points."""

    name: str


@dataclass(frozen=True)
class _FakeEntryPoint:
    """
    Minimal entry-point stub used for registry tests.

    Parameters
    ----------
    name : str
        Entry-point name exposed by the fake distribution.
    value : str
        Raw entry-point target string.
    dist : _FakeDistribution
        Fake distribution metadata owning the entry point.
    loaded : object
        Object or exception returned when the entry point is loaded.
    """

    name: str
    value: str
    dist: _FakeDistribution
    loaded: object

    def load(self) -> object:
        """
        Return or raise the configured load target.

        Parameters
        ----------
        None

        Returns
        -------
        object
            Loaded plugin object for the fake entry point.

        Raises
        ------
        Exception
            Re-raises the configured failure when ``loaded`` is an exception.
        """
        if isinstance(self.loaded, Exception):
            raise self.loaded
        return self.loaded


class _DemoAnalyzer:
    """
    Small analyzer plugin stub.

    Parameters
    ----------
    None
    """

    name = "demo"
    version = "1"
    discovery_globs: tuple[str, ...] = ("*.demo",)

    def supports_path(self, path: Path) -> bool:
        """
        Return whether the fake analyzer accepts the supplied path.

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
        Return an empty deterministic analysis result.

        Parameters
        ----------
        path : pathlib.Path
            Source path supplied to the analyzer.
        root : pathlib.Path
            Repository root supplied to the analyzer.

        Returns
        -------
        repoindex.models.AnalysisResult
            Empty normalized analysis result for the fake plugin.
        """
        del path, root
        return AnalysisResult(
            source_path=Path("demo.demo"),
            module=ModuleArtifact(
                name="demo",
                stable_id="demo:module:demo",
                docstring=None,
                has_docstring=0,
            ),
            classes=(),
            functions=(),
            declarations=(),
            imports=(),
        )


class _DemoBackend(SQLiteIndexBackend):
    """Small backend plugin stub."""

    name = "demo-backend"


def _patch_entry_points(
    monkeypatch: pytest.MonkeyPatch,
    *,
    analyzers: list[_FakeEntryPoint],
    backends: list[_FakeEntryPoint],
) -> None:
    """
    Patch registry entry-point discovery for one test.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest fixture used to override registry discovery hooks.
    analyzers : list[_FakeEntryPoint]
        Fake analyzer entry points exposed during the test.
    backends : list[_FakeEntryPoint]
        Fake backend entry points exposed during the test.

    Returns
    -------
    None
        Registry entry-point discovery is patched in place.
    """

    def fake_group_loader(group: str) -> list[_FakeEntryPoint]:
        if group == registry.ANALYZER_ENTRY_POINT_GROUP:
            return analyzers
        if group == registry.BACKEND_ENTRY_POINT_GROUP:
            return backends
        return []

    monkeypatch.setattr(registry, "_entry_points_for_group", fake_group_loader)


def test_plugin_registrations_report_loaded_skipped_and_duplicate_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Report deterministic plugin discovery diagnostics across families.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest fixture used to patch entry-point discovery.

    Returns
    -------
    None
        The test asserts loaded, skipped, and duplicate plugin statuses.
    """
    _patch_entry_points(
        monkeypatch,
        analyzers=[
            _FakeEntryPoint(
                name="demo-analyzer",
                value="demo:analyzer",
                dist=_FakeDistribution("demo-analyzer"),
                loaded=_DemoAnalyzer,
            ),
            _FakeEntryPoint(
                name="dup-python",
                value="demo:dup",
                dist=_FakeDistribution("dup-analyzer"),
                loaded=type(
                    "_DuplicatePythonAnalyzer",
                    (),
                    {
                        "name": "python",
                        "version": "1",
                        "discovery_globs": ("*.py",),
                        "supports_path": lambda self, path: False,
                        "analyze_file": lambda self, path, root: AnalysisResult(
                            source_path=path,
                            module=ModuleArtifact(
                                name="dup",
                                stable_id="dup:module:dup",
                                docstring=None,
                                has_docstring=0,
                            ),
                            classes=(),
                            functions=(),
                            declarations=(),
                            imports=(),
                        ),
                    },
                ),
            ),
            _FakeEntryPoint(
                name="broken-analyzer",
                value="demo:broken",
                dist=_FakeDistribution("broken-analyzer"),
                loaded=RuntimeError("boom"),
            ),
        ],
        backends=[
            _FakeEntryPoint(
                name="demo-backend",
                value="demo:backend",
                dist=_FakeDistribution("demo-backend"),
                loaded=_DemoBackend,
            ),
        ],
    )

    registrations = registry.plugin_registrations()

    assert any(
        record.family == "analyzer"
        and record.name == "python"
        and record.source == "builtin"
        and record.status == "loaded"
        for record in registrations
    )
    assert any(
        record.family == "analyzer"
        and record.name == "demo"
        and record.provider == "demo-analyzer"
        and record.status == "loaded"
        for record in registrations
    )
    assert any(
        record.family == "analyzer"
        and record.name == "python"
        and record.provider == "dup-analyzer"
        and record.status == "duplicate"
        for record in registrations
    )
    assert any(
        record.family == "analyzer"
        and record.provider == "broken-analyzer"
        and record.status == "skipped"
        and record.detail is not None
        and "RuntimeError" in record.detail
        for record in registrations
    )
    assert any(
        record.family == "backend"
        and record.name == "demo-backend"
        and record.status == "loaded"
        for record in registrations
    )


def test_active_registry_uses_loaded_entry_point_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Activate loaded analyzer and backend plugins from entry points.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest fixture used to patch entry-point discovery and backend config.

    Returns
    -------
    None
        The test asserts entry-point plugins participate in the active
        registry.
    """
    _patch_entry_points(
        monkeypatch,
        analyzers=[
            _FakeEntryPoint(
                name="demo-analyzer",
                value="demo:analyzer",
                dist=_FakeDistribution("demo-analyzer"),
                loaded=_DemoAnalyzer,
            )
        ],
        backends=[
            _FakeEntryPoint(
                name="demo-backend",
                value="demo:backend",
                dist=_FakeDistribution("demo-backend"),
                loaded=_DemoBackend,
            )
        ],
    )
    monkeypatch.setenv(registry.INDEX_BACKEND_ENV_VAR, "demo-backend")

    analyzers = registry.active_language_analyzers()
    backend = registry.active_index_backend()

    assert isinstance(analyzers[0], LanguageAnalyzer)
    assert [analyzer.name for analyzer in analyzers] == ["python", "c", "demo"]
    assert isinstance(backend, IndexBackend)
    assert backend.name == "demo-backend"


def test_plugins_cli_emits_json_registration_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Emit plugin registrations through the dedicated CLI command.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest fixture used to patch entry-point discovery and argv.
    capsys : pytest.CaptureFixture[str]
        Pytest fixture used to capture CLI output.

    Returns
    -------
    None
        The test asserts the CLI JSON includes discovered plugin records.
    """
    _patch_entry_points(
        monkeypatch,
        analyzers=[
            _FakeEntryPoint(
                name="demo-analyzer",
                value="demo:analyzer",
                dist=_FakeDistribution("demo-analyzer"),
                loaded=_DemoAnalyzer,
            )
        ],
        backends=[],
    )
    monkeypatch.setattr(sys, "argv", ["repoindex", "plugins", "--json"])

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "plugins"
    assert payload["status"] == "ok"
    assert any(
        row["family"] == "analyzer"
        and row["name"] == "demo"
        and row["provider"] == "demo-analyzer"
        and row["status"] == "loaded"
        for row in payload["results"]
    )
