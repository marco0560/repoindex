from __future__ import annotations

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
    raw = query.strip()
    lowered = raw.lower()
    tokens = lowered.split()

    return QueryIntent(
        raw=raw,
        is_identifier_query=("_" in raw) or raw.isidentifier(),
        is_multi_term=len(tokens) > 1,
        is_test_related=("test" in lowered) or ("tests" in lowered),
    )
