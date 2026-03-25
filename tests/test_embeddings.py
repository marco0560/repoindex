"""Deterministic tests for the local embedding backend and retrieval channel."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from repoindex.cli import main
from repoindex.indexer import index_repo
from repoindex.query.exact import find_symbol
from repoindex.semantic.embeddings import (
    EMBEDDING_BACKEND,
    EMBEDDING_DIM,
    EMBEDDING_VERSION,
    embed_text,
)
from repoindex.semantic.search import embedding_candidates
from repoindex.storage import get_db_path, init_db


def _write_embedding_fixture(root: Path) -> None:
    """
    Write a small package used for embedding-channel tests.

    Parameters
    ----------
    root : pathlib.Path
        Temporary repository root to populate.

    Returns
    -------
    None
        The fixture files are created under ``root``.
    """
    pkg = root / "pkg"
    pkg.mkdir()

    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "sample.py").write_text(
        '"""Embedding fixture module."""\n'
        "\n"
        "def validate_schema_rules():\n"
        '    """Validate schema migration rules for repository metadata."""\n'
        "    return 1\n"
        "\n"
        "def docstring_audit():\n"
        '    """Audit numpy docstring sections and required parameters."""\n'
        "    return 1\n",
        encoding="utf-8",
    )


def test_embed_text_is_deterministic_and_normalized() -> None:
    """
    Ensure the local embedding backend is deterministic and normalized.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts backend determinism and vector shape.
    """
    first = embed_text("schema migration rules")
    second = embed_text("schema migration rules")

    assert first == second
    assert len(first) == EMBEDDING_DIM
    assert round(sum(value * value for value in first), 6) == 1.0


def test_index_repo_persists_symbol_embeddings(tmp_path: Path) -> None:
    """
    Ensure indexing stores one deterministic embedding per indexed symbol.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts stored embedding metadata and row counts.
    """
    _write_embedding_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        symbol_count = conn.execute("SELECT COUNT(*) FROM symbol_index").fetchone()[0]
        embedding_rows = conn.execute("""
            SELECT object_type, backend, version, dim
            FROM embeddings
            ORDER BY object_type, object_id
            """).fetchall()
    finally:
        conn.close()

    assert len(embedding_rows) == symbol_count
    assert all(
        row == ("symbol", EMBEDDING_BACKEND, EMBEDDING_VERSION, EMBEDDING_DIM)
        for row in embedding_rows
    )


def test_embedding_candidates_are_deterministic_and_overlap(tmp_path: Path) -> None:
    """
    Ensure similar phrasings produce overlapping embedding-channel results.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts deterministic rankings and overlapping top results.
    """
    _write_embedding_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    first = embedding_candidates(
        tmp_path,
        "schema migration",
        limit=5,
        min_score=0.1,
    )
    second = embedding_candidates(
        tmp_path,
        "migrate schema rules",
        limit=5,
        min_score=0.1,
    )
    repeated = embedding_candidates(
        tmp_path,
        "schema migration",
        limit=5,
        min_score=0.1,
    )

    assert first == repeated
    assert first
    assert second

    first_symbols = {symbol for _score, symbol in first}
    second_symbols = {symbol for _score, symbol in second}
    assert first_symbols & second_symbols


def test_embedding_channel_does_not_regress_exact_symbol_lookup(tmp_path: Path) -> None:
    """
    Ensure exact symbol lookup remains unchanged after embedding indexing.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts exact symbol lookup still returns the target function.
    """
    _write_embedding_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    rows = find_symbol(tmp_path, "validate_schema_rules")
    assert rows == [
        (
            "function",
            "pkg.sample",
            "validate_schema_rules",
            str(tmp_path / "pkg" / "sample.py"),
            3,
        )
    ]


def test_embeddings_cli_prints_backend_and_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Verify the embedding inspection CLI path.

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
        The test asserts backend metadata and a ranked match line.
    """
    _write_embedding_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["repoindex", "embeddings", "schema migration rules", "--limit", "2"],
    )

    assert main() == 0
    captured = capsys.readouterr()
    assert "backend: hash-v1 version=1 dim=128" in captured.out
    assert "pkg.sample.validate_schema_rules" in captured.out
