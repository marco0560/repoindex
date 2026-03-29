"""Deterministic tests for the local embedding backend and retrieval channel."""

from __future__ import annotations

import sqlite3
import sys
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


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


def test_c_embedding_candidates_include_include_context(tmp_path: Path) -> None:
    """
    Include C module comments and include context in semantic retrieval.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts embedding retrieval can match C include-context text.
    """
    native = tmp_path / "native"
    native.mkdir()
    (native / "sample.h").write_text(
        "struct Node { int value; };\n",
        encoding="utf-8",
    )
    (native / "sample.c").write_text(
        "/* Vector reduction implementation. */\n"
        '#include "native/sample.h"\n'
        "#include <stdio.h>\n"
        "\n"
        "int public_api(void) {\n"
        "    return 1;\n"
        "}\n",
        encoding="utf-8",
    )

    init_db(tmp_path)
    index_repo(tmp_path)

    results = embedding_candidates(
        tmp_path,
        "vector reduction stdio sample header",
        limit=5,
        min_score=0.1,
    )

    assert results
    symbols = {symbol for _score, symbol in results}
    assert (
        "module",
        "native.sample",
        "native.sample",
        str(tmp_path / "native" / "sample.c"),
        1,
    ) in symbols
    assert (
        "function",
        "native.sample",
        "public_api",
        str(tmp_path / "native" / "sample.c"),
        5,
    ) in symbols


def test_c_embedding_candidates_include_header_source_pairing(tmp_path: Path) -> None:
    """
    Include C header and source pairing context in semantic retrieval.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts semantic retrieval can match paired header/source text.
    """
    native = tmp_path / "native"
    native.mkdir()
    (native / "sample.h").write_text(
        "struct Node { int value; };\n",
        encoding="utf-8",
    )
    (native / "sample.c").write_text(
        '#include "native/sample.h"\n'
        "\n"
        "int public_api(void) {\n"
        "    return 1;\n"
        "}\n",
        encoding="utf-8",
    )

    init_db(tmp_path)
    index_repo(tmp_path)

    header_results = embedding_candidates(
        tmp_path,
        "paired header native sample h",
        limit=5,
        min_score=0.1,
    )
    assert header_results
    header_symbols = {symbol for _score, symbol in header_results}
    assert (
        "function",
        "native.sample",
        "public_api",
        str(tmp_path / "native" / "sample.c"),
        3,
    ) in header_symbols

    source_results = embedding_candidates(
        tmp_path,
        "paired source native sample c",
        limit=5,
        min_score=0.1,
    )
    assert source_results
    source_symbols = {symbol for _score, symbol in source_results}
    assert (
        "struct",
        "native.sample",
        "Node",
        str(tmp_path / "native" / "sample.h"),
        1,
    ) in source_symbols


def test_python_embedding_candidates_include_fixture_assertion_context(
    tmp_path: Path,
) -> None:
    """
    Include Python fixture, setup, and assertion context in semantic retrieval.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts embedding retrieval can match Python semantic-unit
        context lines.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        '"""Validation helpers."""\n'
        "\n"
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def payload_fixture():\n"
        "    return 1\n"
        "\n"
        "def setup_function():\n"
        "    return None\n"
        "\n"
        "def test_payload(payload_fixture):\n"
        '    """Validate payload behavior."""\n'
        "    assert payload_fixture == 1\n",
        encoding="utf-8",
    )

    init_db(tmp_path)
    index_repo(tmp_path)

    fixture_results = embedding_candidates(
        tmp_path,
        "pytest fixture payload",
        limit=5,
        min_score=0.1,
    )
    assert fixture_results
    fixture_symbols = {symbol for _score, symbol in fixture_results}
    assert (
        "function",
        "tests.test_sample",
        "payload_fixture",
        str(tmp_path / "tests" / "test_sample.py"),
        6,
    ) in fixture_symbols

    setup_results = embedding_candidates(
        tmp_path,
        "setup function validation",
        limit=5,
        min_score=0.1,
    )
    assert setup_results
    setup_symbols = {symbol for _score, symbol in setup_results}
    assert (
        "function",
        "tests.test_sample",
        "setup_function",
        str(tmp_path / "tests" / "test_sample.py"),
        9,
    ) in setup_symbols

    assertion_results = embedding_candidates(
        tmp_path,
        "assertions payload validation",
        limit=5,
        min_score=0.1,
    )
    assert assertion_results
    assertion_symbols = {symbol for _score, symbol in assertion_results}
    assert (
        "function",
        "tests.test_sample",
        "test_payload",
        str(tmp_path / "tests" / "test_sample.py"),
        12,
    ) in assertion_symbols


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
