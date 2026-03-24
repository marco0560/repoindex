"""Deterministic query-intent classification for retrieval routing."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryIntent:
    """
    Structured classification of a query.

    Parameters
    ----------
    raw : str
        Original query string.
    is_identifier_query : bool
        Whether the query looks like a single identifier or symbol lookup.
    is_multi_term : bool
        Whether the query contains multiple whitespace-separated terms.
    is_test_related : bool
        Whether the query explicitly targets tests.
    is_script_related : bool
        Whether the query explicitly targets scripts.

    Returns
    -------
    None
        Dataclasses do not return a value from initialization.

    Notes
    -----
    This model is intentionally structural and repository-agnostic.
    """

    raw: str
    is_identifier_query: bool
    is_multi_term: bool
    is_test_related: bool
    is_script_related: bool


def classify_query(query: str) -> QueryIntent:
    """
    Classify a query into structural intent categories.

    Parameters
    ----------
    query : str
        Raw user query string.

    Returns
    -------
    QueryIntent
        Structured intent flags describing the shape of the query.

    Notes
    -----
    Classification is deterministic and repository-agnostic. It avoids
    domain-specific keywords and relies only on query structure.
    """
    q = query.strip()
    tokens = [t for t in q.split() if t]

    is_identifier_query = bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", q))
    is_multi_term = len(tokens) >= 2

    lowered = q.lower()

    is_test_related = any(kw in lowered for kw in ("test", "tests", "pytest"))

    is_script_related = any(
        kw in lowered for kw in ("script", "scripts", "cli", "command")
    )

    return QueryIntent(
        raw=q,
        is_identifier_query=is_identifier_query,
        is_multi_term=is_multi_term,
        is_test_related=is_test_related,
        is_script_related=is_script_related,
    )
