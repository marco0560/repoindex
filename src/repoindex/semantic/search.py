"""Deterministic search helpers for stored semantic embeddings."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.prefix import normalize_prefix, prefix_clause
from repoindex.semantic.embeddings import (
    deserialize_vector,
    embed_text,
    get_embedding_backend,
)
from repoindex.storage import get_db_path
from repoindex.types import ChannelResults, SymbolRow


def _dot(left: list[float], right: list[float]) -> float:
    """
    Compute a dot product between normalized vectors.

    Parameters
    ----------
    left : list[float]
        Left embedding vector.
    right : list[float]
        Right embedding vector.

    Returns
    -------
    float
        Dot-product similarity score.
    """
    return sum(a * b for a, b in zip(left, right, strict=True))


def embedding_candidates(
    root: Path,
    query: str,
    *,
    limit: int,
    min_score: float,
    prefix: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> ChannelResults:
    """
    Return ranked symbol candidates using stored embedding similarity.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index database.
    query : str
        User query string.
    limit : int
        Maximum number of ranked results to return.
    min_score : float
        Minimum similarity threshold for emitted results.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict matched symbol files.
    conn : sqlite3.Connection | None, optional
        Existing database connection to reuse. When omitted, the function
        opens and closes its own connection.

    Returns
    -------
    repoindex.types.ChannelResults
        Ranked symbol candidates ordered by descending similarity and stable
        symbol identity.
    """
    owns_connection = conn is None
    normalized_prefix = normalize_prefix(root, prefix)
    if conn is None:
        conn = sqlite3.connect(get_db_path(root))

    backend = get_embedding_backend()
    query_vector = embed_text(query)
    if not any(query_vector):
        return []

    try:
        prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
        rows = conn.execute(
            f"""
            SELECT
                s.type,
                s.module_name,
                s.name,
                f.path,
                s.lineno,
                e.version,
                e.dim,
                e.vector
            FROM embeddings e
            JOIN symbol_index s
              ON e.object_type = 'symbol'
             AND e.object_id = s.id
            JOIN files f
              ON s.file_id = f.id
            WHERE e.backend = ? AND e.version = ?
            {prefix_sql}
            ORDER BY s.module_name, s.name, f.path, s.lineno, s.type
            """,
            (backend.name, backend.version, *prefix_params),
        ).fetchall()

        results: ChannelResults = []

        for row in rows:
            symbol: SymbolRow = (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                int(row[4]),
            )
            version = str(row[5])
            dim = int(row[6])
            blob = bytes(row[7])
            if version != backend.version or dim != backend.dim:
                continue

            score = _dot(query_vector, deserialize_vector(blob, dim=dim))
            if score < min_score:
                continue

            results.append((score, symbol))

        results.sort(
            key=lambda item: (
                -item[0],
                item[1][1],
                item[1][2],
                item[1][3],
                item[1][4],
                item[1][0],
            )
        )
        return results[:limit]
    finally:
        if owns_connection:
            conn.close()
