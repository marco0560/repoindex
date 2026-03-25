"""Deterministic tests for incremental indexing behavior."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from repoindex.cli import main
from repoindex.indexer import index_repo
from repoindex.query.exact import find_symbol
from repoindex.scanner import file_metadata
from repoindex.semantic.embeddings import EmbeddingBackendSpec
from repoindex.storage import get_db_path, init_db


def _write_module(path: Path, source: str) -> None:
    """
    Write one Python module fixture.

    Parameters
    ----------
    path : pathlib.Path
        Module path to create or replace.
    source : str
        Python source code written to ``path``.

    Returns
    -------
    None
        The file is written in place.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_index_repo_reuses_unchanged_files(tmp_path: Path) -> None:
    """
    Ensure an unchanged repository is not reparsed on the second run.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts deterministic reuse counts and preserved embeddings.
    """
    module = tmp_path / "pkg" / "sample.py"
    _write_module(
        module,
        '"""Module doc."""\n'
        "\n"
        "def demo():\n"
        '    """Return a constant."""\n'
        "    return 1\n",
    )

    init_db(tmp_path)
    first = index_repo(tmp_path)
    second = index_repo(tmp_path)

    assert first.indexed == 1
    assert first.reused == 0
    assert first.deleted == 0
    assert first.embeddings_recomputed > 0

    assert second.indexed == 0
    assert second.reused == 1
    assert second.deleted == 0
    assert second.embeddings_recomputed == 0
    assert second.embeddings_reused == first.embeddings_recomputed


def test_index_repo_reindexes_changed_files(tmp_path: Path) -> None:
    """
    Ensure content changes trigger reparsing for the modified file only.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts changed-file reindexing and updated symbol contents.
    """
    module = tmp_path / "pkg" / "sample.py"
    _write_module(
        module,
        '"""Module doc."""\n'
        "\n"
        "def demo():\n"
        '    """Return a constant."""\n'
        "    return 1\n",
    )

    init_db(tmp_path)
    first_meta = file_metadata(module)
    index_repo(tmp_path)

    _write_module(
        module,
        '"""Module doc."""\n'
        "\n"
        "def demo():\n"
        '    """Return a constant."""\n'
        "    return 1\n"
        "\n"
        "def extra():\n"
        '    """Return another constant."""\n'
        "    return 2\n",
    )

    second_meta = file_metadata(module)
    report = index_repo(tmp_path)

    assert second_meta["hash"] != first_meta["hash"]
    assert report.indexed == 1
    assert report.reused == 0
    assert report.deleted == 0
    assert report.embeddings_recomputed > 0
    assert find_symbol(tmp_path, "extra")


def test_index_repo_removes_deleted_files(tmp_path: Path) -> None:
    """
    Ensure deleted files are removed while unchanged files are reused.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts deleted-file cleanup and retained reused rows.
    """
    keep_module = tmp_path / "pkg" / "keep.py"
    drop_module = tmp_path / "pkg" / "drop.py"
    _write_module(
        keep_module,
        "def keep():\n" '    """Stay indexed."""\n' "    return 1\n",
    )
    _write_module(
        drop_module,
        "def drop_me():\n" '    """Disappear from the index."""\n' "    return 1\n",
    )

    init_db(tmp_path)
    index_repo(tmp_path)

    drop_module.unlink()
    report = index_repo(tmp_path)

    assert report.indexed == 0
    assert report.reused == 1
    assert report.deleted == 1
    assert find_symbol(tmp_path, "drop_me") == []
    assert find_symbol(tmp_path, "keep")


def test_index_repo_recomputes_embeddings_when_backend_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure backend-version changes invalidate reused embeddings explicitly.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.
    monkeypatch : pytest.MonkeyPatch
        Fixture used to replace the active backend metadata.

    Returns
    -------
    None
        The test asserts backend invalidation triggers reparsing and storage
        of the new backend version.
    """
    module = tmp_path / "pkg" / "sample.py"
    _write_module(
        module,
        "def demo():\n" '    """Return a constant."""\n' "    return 1\n",
    )

    init_db(tmp_path)
    index_repo(tmp_path)

    monkeypatch.setattr(
        "repoindex.indexer.get_embedding_backend",
        lambda: EmbeddingBackendSpec(name="hash-v1", version="2", dim=128),
    )
    report = index_repo(tmp_path)

    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        versions = conn.execute(
            "SELECT DISTINCT version FROM embeddings ORDER BY version"
        ).fetchall()
    finally:
        conn.close()

    assert report.indexed == 1
    assert report.reused == 0
    assert report.embeddings_recomputed > 0
    assert versions == [("2",)]


def test_index_cli_reports_summary_and_decisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Ensure the CLI prints incremental summary lines and explain decisions.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.
    monkeypatch : pytest.MonkeyPatch
        Fixture used to control process state.
    capsys : pytest.CaptureFixture[str]
        Fixture used to capture CLI output.

    Returns
    -------
    None
        The test asserts summary output and per-file explain lines.
    """
    module = tmp_path / "pkg" / "sample.py"
    _write_module(
        module,
        "def demo():\n" '    """Return a constant."""\n' "    return 1\n",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["repoindex", "index", "--explain"])

    assert main() == 0
    captured = capsys.readouterr()
    assert "Indexed: 1" in captured.out
    assert "Reused: 0" in captured.out
    assert "Deleted: 0" in captured.out
    assert "Embeddings recomputed:" in captured.out
    assert "indexed: pkg/sample.py" in captured.out
