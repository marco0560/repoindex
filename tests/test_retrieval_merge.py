"""Regression tests for retrieval merge stability.

Responsibilities
----------------
- Assert channel deduplication, tie-breaking, and cross-family bonuses in merge helpers.
- Validate final merged ordering, provenance metrics, and role/explain data.

Design principles
-----------------
Tests keep merge coverage specific to fix retrieval ordering so merged outputs stay deterministic.

Architectural role
------------------
This module belongs to the **retrieval verification layer** that ensures stable merged outputs for prompts and CLI consumers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from repoindex.query.classifier import classify_query
from repoindex.query.context import (
    MERGE_RESULT_LIMIT,
    _dedupe_channel_results,
    _diversify_merged_symbols,
    _diversify_merged_symbols_explain,
    _merge_ranked_channel_bundles_explain,
)

if TYPE_CHECKING:
    from repoindex.types import ChannelResults, SymbolRow


def _symbol(
    symbol_type: str,
    module_name: str,
    name: str,
    file_path: str,
    lineno: int,
) -> SymbolRow:
    return (symbol_type, module_name, name, file_path, lineno)


def test_dedupe_channel_results_keeps_first_ranked_occurrence() -> None:
    """
    Ensure channel-local deduplication preserves the best-ranked occurrence.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts that duplicate channel entries keep the first rank.
    """
    symbol = _symbol("function", "repoindex.alpha", "run", "src/a.py", 10)
    other = _symbol("function", "repoindex.beta", "run", "src/b.py", 20)
    channel: ChannelResults = [
        (9.0, symbol),
        (8.0, symbol),
        (7.0, other),
    ]

    deduped = _dedupe_channel_results(channel)

    assert deduped == [
        (9.0, symbol),
        (7.0, other),
    ]


def test_merge_ranked_channel_bundles_explain_dedupes_and_orders_ties() -> None:
    """
    Ensure merged output is unique and tie ordering is deterministic.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts deterministic tie ordering and provenance.
    """
    alpha = _symbol("function", "repoindex.alpha", "run", "src/a.py", 10)
    beta = _symbol("function", "repoindex.beta", "run", "src/b.py", 20)

    bundles = [
        (
            "semantic",
            [
                (5.0, beta),
                (4.0, beta),
            ],
        ),
        (
            "symbol",
            [
                (9.0, alpha),
                (8.0, alpha),
            ],
        ),
    ]

    merged, provenance = _merge_ranked_channel_bundles_explain(bundles)

    assert merged == [alpha, beta]
    assert provenance[alpha] == {
        "channels": {"symbol": 9.0},
        "families": {"lexical": 9.0},
        "rrf_score": 1.0,
        "evidence_bonus": 0.0,
        "role_bonus": 0.75,
        "merge_score": 1.75,
        "winner": "symbol",
    }
    assert provenance[beta] == {
        "channels": {"semantic": 5.0},
        "families": {"semantic": 5.0},
        "rrf_score": 1.0,
        "evidence_bonus": 0.0,
        "role_bonus": 0.75,
        "merge_score": 1.75,
        "winner": "semantic",
    }


def test_merge_ranked_channel_bundles_explain_rewards_cross_family_support() -> None:
    """
    Prefer symbols supported by more than one evidence family.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts the merge layer applies a deterministic bonus when a
        symbol is corroborated by both lexical and semantic evidence.
    """
    alpha = _symbol("function", "repoindex.alpha", "run", "src/a.py", 10)
    beta = _symbol("function", "repoindex.beta", "run", "src/b.py", 20)
    gamma = _symbol("function", "repoindex.gamma", "run", "src/c.py", 30)

    bundles = [
        (
            "symbol",
            [
                (9.0, alpha),
                (8.0, beta),
            ],
        ),
        (
            "semantic",
            [
                (5.0, gamma),
                (4.0, beta),
            ],
        ),
    ]

    merged, provenance = _merge_ranked_channel_bundles_explain(bundles)

    assert merged[:2] == [beta, alpha]
    assert provenance[beta] == {
        "channels": {"symbol": 8.0, "semantic": 4.0},
        "families": {"lexical": 8.0, "semantic": 4.0},
        "rrf_score": 1.0,
        "evidence_bonus": 0.15,
        "role_bonus": 0.75,
        "merge_score": 1.9,
        "winner": "symbol",
    }


def test_merge_ranked_channel_bundles_explain_applies_role_bonus() -> None:
    """
    Expose merge-time role contribution separately from family evidence.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts implementation symbols gain a visible merge bonus
        over tests for default non-test queries.
    """
    implementation = _symbol("function", "pkg.core", "cache_flow", "src/core.py", 10)
    test_symbol = _symbol(
        "function",
        "tests.test_core",
        "cache_flow_test",
        "tests/test_core.py",
        20,
    )
    bundles = [
        (
            "semantic",
            [
                (5.0, test_symbol),
                (4.0, implementation),
            ],
        )
    ]

    merged, provenance = _merge_ranked_channel_bundles_explain(
        bundles,
        intent=classify_query("cache invalidation"),
    )

    assert merged[:2] == [implementation, test_symbol]
    assert provenance[implementation] == {
        "channels": {"semantic": 4.0},
        "families": {"semantic": 4.0},
        "rrf_score": 0.5,
        "evidence_bonus": 0.0,
        "role_bonus": 0.75,
        "merge_score": 1.25,
        "winner": "semantic",
    }
    assert provenance[test_symbol] == {
        "channels": {"semantic": 5.0},
        "families": {"semantic": 5.0},
        "rrf_score": 1.0,
        "evidence_bonus": 0.0,
        "role_bonus": -1.0,
        "merge_score": 0.0,
        "winner": "semantic",
    }


def test_merge_ranked_channel_bundles_explain_caps_output() -> None:
    """
    Ensure merged output is capped by the module-level limit.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts enforcement of the merged-output cap.
    """
    bundles = [
        (
            "symbol",
            [
                (
                    float(MERGE_RESULT_LIMIT - idx),
                    _symbol(
                        "function",
                        f"repoindex.module_{idx:02d}",
                        "run",
                        f"src/module_{idx:02d}.py",
                        idx,
                    ),
                )
                for idx in range(MERGE_RESULT_LIMIT + 3)
            ],
        )
    ]

    merged, _ = _merge_ranked_channel_bundles_explain(bundles)

    assert len(merged) == MERGE_RESULT_LIMIT


def test_diversify_merged_symbols_caps_one_symbol_per_file() -> None:
    """
    Keep one file from monopolizing the merged top-symbol block.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts later files are allowed in once an earlier file
        already contributed one symbol.
    """
    ranked = [
        _symbol("function", "repoindex.alpha", "first", "src/a.py", 10),
        _symbol("function", "repoindex.alpha", "second", "src/a.py", 20),
        _symbol("function", "repoindex.beta", "run", "src/b.py", 30),
    ]

    diversified = _diversify_merged_symbols(ranked)

    assert diversified[:2] == [ranked[0], ranked[2]]


def test_diversify_merged_symbols_limits_test_role_monopoly() -> None:
    """
    Prevent test files from crowding out implementation results by default.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts excess test-role symbols are deferred until an
        implementation symbol is included.
    """
    ranked = [
        _symbol("function", "tests.alpha", "one", "tests/test_a.py", 10),
        _symbol("function", "tests.beta", "two", "tests/test_b.py", 20),
        _symbol("function", "tests.gamma", "three", "tests/test_c.py", 30),
        _symbol("function", "repoindex.core", "run", "src/core.py", 40),
    ]

    diversified = _diversify_merged_symbols(ranked)

    assert diversified[:3] == [ranked[0], ranked[1], ranked[3]]


def test_diversify_merged_symbols_limits_language_monopoly_when_mixed() -> None:
    """
    Prevent one language family from crowding out another in mixed results.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts a C result is admitted during primary selection when
        Python otherwise dominates a mixed-language ranked list.
    """
    ranked = [
        _symbol("function", "pkg.alpha", "one", "src/a.py", 10),
        _symbol("function", "pkg.beta", "two", "src/b.py", 20),
        _symbol("function", "pkg.gamma", "three", "src/c.py", 30),
        _symbol("function", "pkg.delta", "four", "src/d.py", 40),
        _symbol("function", "pkg.epsilon", "five", "src/e.py", 50),
        _symbol("function", "native.sample", "helper", "native/sample.c", 60),
    ]

    diversified = _diversify_merged_symbols(ranked)

    assert diversified[:5] == [ranked[0], ranked[1], ranked[2], ranked[3], ranked[5]]


def test_diversify_merged_symbols_explain_reports_selected_and_deferred() -> None:
    """
    Expose deterministic diversity diagnostics for explain mode.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts selected stages and deferred reasons are recorded.
    """
    ranked = [
        _symbol("function", "tests.alpha", "one", "tests/test_a.py", 10),
        _symbol("function", "tests.beta", "two", "tests/test_b.py", 20),
        _symbol("function", "tests.gamma", "three", "tests/test_c.py", 30),
        _symbol("function", "repoindex.core", "run", "src/core.py", 40),
    ]

    diversified, diagnostics = _diversify_merged_symbols_explain(ranked)

    assert diversified[:3] == [ranked[0], ranked[1], ranked[3]]
    assert diagnostics["selected"][0]["selection_stage"] == "primary"
    assert diagnostics["selected"][0]["language"] == "python"
    assert diagnostics["selected"][2]["selection_stage"] == "primary"
    assert diagnostics["deferred"][0]["reason"] == "role_cap"


def test_diversify_merged_symbols_explain_does_not_requeue_deferred_file_caps() -> None:
    """
    Keep deferred-stage file caps from mutating the active iteration list.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts deferred file-cap entries remain diagnostics only and
        do not loop indefinitely during deferred selection.
    """
    ranked = [
        _symbol("function", "pkg.alpha", "one", "src/shared.py", 10),
        _symbol("function", "pkg.alpha", "two", "src/shared.py", 20),
        _symbol("function", "pkg.beta", "run", "src/beta.py", 30),
    ]

    diversified, diagnostics = _diversify_merged_symbols_explain(ranked)

    assert diversified == [ranked[0], ranked[2]]
    assert diagnostics["deferred"] == [
        {
            "type": "function",
            "module": "pkg.alpha",
            "name": "two",
            "file": "src/shared.py",
            "lineno": 20,
            "role": "implementation",
            "language": "python",
            "reason": "file_cap",
        }
    ]


def test_diversify_merged_symbols_explain_reports_language_cap() -> None:
    """
    Surface language-cap deferrals in explain diagnostics.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts mixed-language deferrals record language metadata and
        the dedicated deferral reason.
    """
    ranked = [
        _symbol("function", "pkg.alpha", "one", "src/a.py", 10),
        _symbol("function", "pkg.beta", "two", "src/b.py", 20),
        _symbol("function", "pkg.gamma", "three", "src/c.py", 30),
        _symbol("function", "pkg.delta", "four", "src/d.py", 40),
        _symbol("function", "pkg.epsilon", "five", "src/e.py", 50),
        _symbol("function", "native.sample", "helper", "native/sample.c", 60),
    ]

    diversified, diagnostics = _diversify_merged_symbols_explain(ranked)

    assert diversified[:5] == [ranked[0], ranked[1], ranked[2], ranked[3], ranked[5]]
    assert diagnostics["selected"][4]["language"] == "c"
    assert diagnostics["deferred"][0] == {
        "type": "function",
        "module": "pkg.epsilon",
        "name": "five",
        "file": "src/e.py",
        "lineno": 50,
        "role": "implementation",
        "language": "python",
        "reason": "language_cap",
    }
