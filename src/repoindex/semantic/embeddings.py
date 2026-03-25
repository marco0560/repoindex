"""Deterministic local embedding backend for repoindex."""

from __future__ import annotations

import hashlib
import math
import re
import struct

EMBEDDING_BACKEND = "hash-v1"
EMBEDDING_DIM = 128


def _tokenize_embedding_text(text: str) -> list[str]:
    """
    Tokenize text for deterministic local embedding generation.

    Parameters
    ----------
    text : str
        Raw text to tokenize.

    Returns
    -------
    list[str]
        Lowercased alphanumeric tokens in source order.
    """
    return re.findall(r"[a-z0-9_]+", text.lower())


def embed_text(text: str) -> list[float]:
    """
    Embed text using the deterministic in-repo backend.

    Parameters
    ----------
    text : str
        Text payload to embed.

    Returns
    -------
    list[float]
        L2-normalized embedding vector with fixed dimensionality.
    """
    vector = [0.0] * EMBEDDING_DIM
    tokens = _tokenize_embedding_text(text)

    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], byteorder="big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0] * EMBEDDING_DIM

    return [value / norm for value in vector]


def serialize_vector(vector: list[float]) -> bytes:
    """
    Serialize a dense embedding vector for SQLite storage.

    Parameters
    ----------
    vector : list[float]
        Dense embedding vector.

    Returns
    -------
    bytes
        Binary representation of the vector.
    """
    return struct.pack(f"<{len(vector)}f", *vector)


def deserialize_vector(blob: bytes, *, dim: int) -> list[float]:
    """
    Deserialize a dense embedding vector from SQLite storage.

    Parameters
    ----------
    blob : bytes
        Stored binary vector payload.
    dim : int
        Expected vector dimensionality.

    Returns
    -------
    list[float]
        Dense embedding vector.
    """
    return list(struct.unpack(f"<{dim}f", blob))
