"""Deterministic tests for static call-graph indexing and inspection."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from repoindex.cli import build_parser, main
from repoindex.indexer import index_repo
from repoindex.query.context import context_for
from repoindex.query.exact import find_call_edges, find_callable_refs
from repoindex.storage import get_db_path, init_db


def _write_fixture(root: Path) -> None:
    """
    Write a small multi-module package used for call-graph tests.

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
    (pkg / "b.py").write_text(
        '"""Helpers for import resolution tests."""\n'
        "\n"
        "def imported_helper():\n"
        '    """Return a constant value."""\n'
        "    return 1\n",
        encoding="utf-8",
    )
    (pkg / "a.py").write_text(
        '"""Call-graph fixture module."""\n'
        "\n"
        "from pkg.b import imported_helper as external\n"
        "import pkg.b as helpers\n"
        "\n"
        "def helper(value=0):\n"
        '    """Return the given value."""\n'
        "    return value\n"
        "\n"
        "def dynamic(callback):\n"
        '    """Trigger unresolved callback calls."""\n'
        "    callback()\n"
        "    callback()\n"
        "    return 1\n"
        "\n"
        "def caller():\n"
        '    """Exercise same-module static calls."""\n'
        "    helper()\n"
        "    helper(1)\n"
        "    return dynamic(helper)\n"
        "\n"
        "def registry():\n"
        '    """Return callable references without invoking them."""\n'
        "    return {\n"
        '        "local": helper,\n'
        '        "imported": external,\n'
        '        "method": Demo.helper,\n'
        "    }\n"
        "\n"
        "def imported_caller():\n"
        '    """Exercise straightforward imported call resolution."""\n'
        "    external()\n"
        "    helpers.imported_helper()\n"
        "    return 1\n"
        "\n"
        "class Demo:\n"
        "    def helper(self):\n"
        '        """Return a constant value."""\n'
        "        return 1\n"
        "\n"
        "    def caller(self):\n"
        '        """Exercise self method resolution."""\n'
        "        self.helper()\n"
        "        self.helper()\n"
        "        return 1\n",
        encoding="utf-8",
    )


def test_call_edges_are_resolved_and_deduplicated(tmp_path: Path) -> None:
    """
    Index a fixture package and assert deterministic call-edge rows.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts exact stored call-edge rows and helper lookups.
    """
    _write_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        rows = conn.execute("""
            SELECT caller_module, caller_name, callee_module, callee_name, resolved
            FROM call_edges
            ORDER BY
                caller_module,
                caller_name,
                COALESCE(callee_module, ''),
                COALESCE(callee_name, ''),
                resolved
            """).fetchall()
    finally:
        conn.close()

    assert rows == [
        ("pkg.a", "Demo.caller", "pkg.a", "Demo.helper", 1),
        ("pkg.a", "caller", "pkg.a", "dynamic", 1),
        ("pkg.a", "caller", "pkg.a", "helper", 1),
        ("pkg.a", "dynamic", None, None, 0),
        ("pkg.a", "imported_caller", "pkg.b", "imported_helper", 1),
    ]

    assert find_call_edges(tmp_path, "caller", module="pkg.a") == [
        ("pkg.a", "caller", "pkg.a", "dynamic", 1),
        ("pkg.a", "caller", "pkg.a", "helper", 1),
    ]
    assert find_call_edges(
        tmp_path,
        "imported_helper",
        module="pkg.b",
        incoming=True,
    ) == [
        ("pkg.a", "imported_caller", "pkg.b", "imported_helper", 1),
    ]

    assert find_callable_refs(tmp_path, "registry", module="pkg.a") == [
        ("pkg.a", "registry", "pkg.a", "Demo.helper", 1),
        ("pkg.a", "registry", "pkg.a", "helper", 1),
        ("pkg.a", "registry", "pkg.b", "imported_helper", 1),
    ]
    assert find_callable_refs(
        tmp_path,
        "helper",
        module="pkg.a",
        incoming=True,
    ) == [
        ("pkg.a", "registry", "pkg.a", "helper", 1),
    ]


def test_chained_attribute_calls_keep_distinct_semantics(tmp_path: Path) -> None:
    """
    Preserve distinct raw call records for chained dynamic attribute calls.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts that chained calls produce distinct raw records and
        index without storage collisions.
    """
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "chain.py").write_text(
        '"""Fixture covering chained dynamic attribute calls."""\n'
        "\n"
        "def chained(text, line, value):\n"
        '    """Exercise chained dynamic attribute calls."""\n'
        "    text.replace(\n"
        '        "\\\\", r"\\\\"\n'
        '    ).replace("{", r"\\\\{").replace("}", r"\\\\}")\n'
        '    line[len("file:") :].strip().strip(\'"\')\n'
        "    str(value).strip().lower()\n",
        encoding="utf-8",
    )

    init_db(tmp_path)
    index_repo(tmp_path)

    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        rows = conn.execute("""
            SELECT kind, base, target, lineno, col_offset
            FROM call_records
            WHERE owner_module = 'pkg.chain' AND owner_name = 'chained'
            ORDER BY lineno, col_offset, kind, base, target
            """).fetchall()
    finally:
        conn.close()

    assert rows == [
        ("attribute", "text", "replace", 5, 9),
        ("attribute", "", "replace", 7, 6),
        ("attribute", "", "replace", 7, 27),
        ("name", "", "len", 8, 9),
        ("attribute", "", "strip", 8, 25),
        ("attribute", "", "strip", 8, 33),
        ("name", "", "str", 9, 4),
        ("attribute", "", "strip", 9, 15),
        ("attribute", "", "lower", 9, 23),
    ]


def test_calls_cli_prints_incoming_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Verify the CLI inspection path for incoming call edges.

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
        The test asserts the printed incoming edge line.
    """
    _write_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repoindex",
            "calls",
            "imported_helper",
            "--module",
            "pkg.b",
            "--incoming",
        ],
    )

    assert main() == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "pkg.a.imported_caller -> pkg.b.imported_helper"


def test_refs_cli_prints_incoming_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Verify the CLI inspection path for incoming callable references.

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
        The test asserts the printed incoming reference line.
    """
    _write_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repoindex",
            "refs",
            "helper",
            "--module",
            "pkg.a",
            "--incoming",
        ],
    )

    assert main() == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "pkg.a.registry => pkg.a.helper"


def test_top_level_help_includes_examples_and_calls_command() -> None:
    """
    Verify the top-level help advertises key commands and examples.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts key help text fragments.
    """
    parser = build_parser()
    help_text = parser.format_help()

    assert 'repoindex embeddings "schema migration rules"' in help_text
    assert "repoindex calls caller" in help_text
    assert "repoindex refs _retrieve_script_candidates --incoming" in help_text
    assert "repoindex context-for --prompt" in help_text
    assert "audit-docstrings" in help_text


def test_context_for_expands_related_cross_module_graph_symbols(
    tmp_path: Path,
) -> None:
    """
    Ensure context expansion pulls in cross-module graph-related symbols.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts graph-derived expansion from call and ref data.
    """
    _write_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    imported_data = json.loads(
        context_for(
            tmp_path,
            "imported_helper",
            as_json=True,
        )
    )
    registry_data = json.loads(
        context_for(
            tmp_path,
            "registry",
            as_json=True,
        )
    )

    imported_related = {
        (row["module"], row["name"])
        for row in imported_data["top_matches"] + imported_data["module_expansion"]
    }
    registry_expansion = {
        (row["module"], row["name"]) for row in registry_data["module_expansion"]
    }

    assert ("pkg.a", "imported_caller") in imported_related
    assert ("pkg.a", "registry") in imported_related
    assert ("pkg.b", "imported_helper") in registry_expansion


def test_context_for_help_shows_incompatibility_and_examples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Verify subcommand help exposes examples and parser-level constraints.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts help text and parser enforcement for context modes.
    """
    with pytest.raises(SystemExit) as help_exit:
        build_parser().parse_args(["context-for", "-h"])

    assert help_exit.value.code == 0

    captured = capsys.readouterr()
    assert "--json | --prompt | --explain" in captured.out
    assert "repoindex context-for --explain" in captured.out

    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(
            ["context-for", "--prompt", "--explain", "static call graph"]
        )

    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(
            ["context-for", "--json", "--prompt", "static call graph"]
        )

    assert exc.value.code == 2
