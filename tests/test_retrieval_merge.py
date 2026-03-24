"""Regression tests for retrieval merge stability."""

from __future__ import annotations

from repoindex.query.context import (
    MERGE_RESULT_LIMIT,
    _dedupe_channel_results,
    _merge_ranked_channel_bundles_explain,
)
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
    assert provenance == {
        alpha: {"symbol": 9.0},
        beta: {"semantic": 5.0},
    }


def test_merge_ranked_channel_bundles_explain_caps_output() -> None:
    """
    Ensure merged output is capped by the module-level limit.
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
