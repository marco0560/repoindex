#!/usr/bin/env python3
"""Provision the local sentence-transformers model used by repoindex."""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

from repoindex.semantic.embeddings import EMBEDDING_BACKEND


def main() -> int:
    """
    Download or verify the configured local embedding model artifact.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Process exit code.
    """
    model = SentenceTransformer(EMBEDDING_BACKEND, device="cpu")
    model.get_sentence_embedding_dimension()
    print(f"Provisioned embedding model: {EMBEDDING_BACKEND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
