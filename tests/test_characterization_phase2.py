"""ADR-004 Phase 2 characterization tests for stable query ordering."""

from __future__ import annotations

import json
from pathlib import Path

from repoindex.indexer import index_repo
from repoindex.query.context import context_for
from repoindex.query.exact import find_symbol
from repoindex.storage import init_db


def _write_phase2_fixture(root: Path) -> None:
    """
    Write a small duplicate-symbol fixture for characterization tests.

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
    (pkg / "zeta.py").write_text(
        '"""Late-sorted duplicate symbol fixture."""\n'
        "\n"
        "def shared_symbol():\n"
        '    """Return the zeta duplicate."""\n'
        "    return 2\n",
        encoding="utf-8",
    )
    (pkg / "alpha.py").write_text(
        '"""Early-sorted duplicate symbol fixture."""\n'
        "\n"
        "def shared_symbol():\n"
        '    """Return the alpha duplicate."""\n'
        "    return 1\n",
        encoding="utf-8",
    )


def _write_phase12_role_fixture(root: Path) -> None:
    """
    Write a small implementation-and-test fixture for role-aware retrieval.

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
    tests_dir = root / "tests"
    pkg.mkdir()
    tests_dir.mkdir()

    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")

    (pkg / "core.py").write_text(
        '"""Cache invalidation implementation module."""\n'
        "\n"
        "def cache_flow():\n"
        '    """Cache invalidation engine for production writes."""\n'
        "    return True\n",
        encoding="utf-8",
    )
    (tests_dir / "test_core.py").write_text(
        '"""Cache invalidation tests module."""\n'
        "\n"
        "def cache_flow_test():\n"
        '    """Cache invalidation tests for regression coverage."""\n'
        "    return True\n",
        encoding="utf-8",
    )


def test_index_report_decisions_are_sorted_deterministically(tmp_path: Path) -> None:
    """
    Preserve deterministic per-file decision ordering in index reports.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts stable decision ordering independent of file creation
        order.
    """
    _write_phase2_fixture(tmp_path)
    init_db(tmp_path)

    report = index_repo(tmp_path)

    assert [(row.action, row.path, row.reason) for row in report.decisions] == [
        ("indexed", str(tmp_path / "pkg" / "__init__.py"), "new file"),
        ("indexed", str(tmp_path / "pkg" / "alpha.py"), "new file"),
        ("indexed", str(tmp_path / "pkg" / "zeta.py"), "new file"),
    ]


def test_find_symbol_orders_duplicate_matches_by_module(tmp_path: Path) -> None:
    """
    Preserve deterministic ordering for duplicate exact-symbol matches.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts the exact-match ordering contract used by callers and
        CLI rendering.
    """
    _write_phase2_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    assert find_symbol(tmp_path, "shared_symbol") == [
        (
            "function",
            "pkg.alpha",
            "shared_symbol",
            str(tmp_path / "pkg" / "alpha.py"),
            3,
        ),
        (
            "function",
            "pkg.zeta",
            "shared_symbol",
            str(tmp_path / "pkg" / "zeta.py"),
            3,
        ),
    ]


def test_context_for_json_is_stable_across_repeated_runs(tmp_path: Path) -> None:
    """
    Preserve deterministic JSON ordering for repeated context retrieval.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts repeated JSON output remains byte-for-byte equivalent
        after parsing and that ranked matches retain a stable order.
    """
    _write_phase2_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    first = json.loads(context_for(tmp_path, "shared_symbol", as_json=True))
    second = json.loads(context_for(tmp_path, "shared_symbol", as_json=True))

    assert first == second
    assert [row["module"] for row in first["top_matches"]] == [
        "pkg.alpha",
        "pkg.zeta",
    ]


def test_context_for_prefers_implementation_unless_tests_are_requested(
    tmp_path: Path,
) -> None:
    """
    Preserve the Phase 12 implementation-first ranking contract.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts implementation files rank ahead of tests by default
        and that explicit test queries flip that preference.
    """
    _write_phase12_role_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    default_context = json.loads(
        context_for(tmp_path, "cache invalidation", as_json=True)
    )
    test_context = json.loads(
        context_for(tmp_path, "cache invalidation tests", as_json=True)
    )

    assert default_context["top_matches"][0]["module"] == "pkg.core"
    assert test_context["top_matches"][0]["module"] == "tests.test_core"


def test_context_for_explain_reports_phase_17_retrieval_plan(tmp_path: Path) -> None:
    """
    Expose the deterministic Phase 17 retrieval plan in explain output.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest.

    Returns
    -------
    None
        The test asserts explain output reflects the planner for test and
        architecture-oriented queries.
    """
    _write_phase12_role_fixture(tmp_path)
    init_db(tmp_path)
    index_repo(tmp_path)

    test_payload = json.loads(
        context_for(tmp_path, "cache invalidation tests", as_json=True, explain=True)
    )
    architecture_payload = json.loads(
        context_for(
            tmp_path,
            "architecture graph cache flow",
            as_json=True,
            explain=True,
        )
    )

    test_explain = test_payload["explain"]
    assert test_explain["intent"]["primary_intent"] == "test"
    assert test_explain["planner"] == {
        "primary_intent": "test",
        "channels": ["test", "symbol", "embedding", "semantic"],
        "include_doc_issues": False,
        "include_include_graph": False,
        "include_references": True,
    }

    architecture_explain = architecture_payload["explain"]
    assert architecture_explain["intent"]["primary_intent"] == "architecture"
    assert architecture_explain["planner"]["channels"] == [
        "symbol",
        "semantic",
        "embedding",
    ]
    assert architecture_explain["planner"]["include_include_graph"] is True
