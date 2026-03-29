#!/usr/bin/env python3
"""Provision the local sentence-transformers model used by repoindex."""

from __future__ import annotations

import sys

from repoindex.semantic.embeddings import (
    EMBEDDING_BACKEND,
    EmbeddingBackendError,
    provision_embedding_model,
)


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
    try:
        provision_embedding_model(quiet=True)
    except EmbeddingBackendError as exc:
        print(f"[repoindex] {exc}", file=sys.stderr)
        return 1
    print(f"Provisioned embedding model: {EMBEDDING_BACKEND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
