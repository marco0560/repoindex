"""Deterministic local embedding backend for repoindex."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

    class _EmbeddingVector(Protocol):
        def tolist(self) -> list[float]: ...

    class _EmbeddingArray(Protocol):
        def __getitem__(self, index: int) -> _EmbeddingVector: ...

    class _EmbeddingModel(Protocol):
        def get_sentence_embedding_dimension(self) -> int: ...

        def encode(
            self,
            sentences: Sequence[str],
            *,
            convert_to_numpy: bool,
            normalize_embeddings: bool,
            show_progress_bar: bool,
        ) -> _EmbeddingArray: ...


EMBEDDING_BACKEND = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_VERSION = "1"
EMBEDDING_DIM = 384
_DEPENDENCY_INSTALL_HINT = (
    "Install the package with the semantic extra, for example "
    "'pip install -e .[semantic]'."
)
_MISSING_MODEL_HINT = (
    "The model must already exist in the local Hugging Face cache because "
    "repoindex runs in offline mode."
)
_MODEL_LOAD_HINT = "The local model artifact could not be loaded in offline mode."


@dataclass(frozen=True)
class EmbeddingBackendSpec:
    """
    Stable metadata describing the active embedding backend.

    Parameters
    ----------
    name : str
        Backend identifier stored in the index.
    version : str
        Backend-specific version used for explicit invalidation.
    dim : int
        Fixed vector dimensionality.
    """

    name: str
    version: str
    dim: int


def get_embedding_backend() -> EmbeddingBackendSpec:
    """
    Return the active embedding backend specification.

    Parameters
    ----------
    None

    Returns
    -------
    EmbeddingBackendSpec
        Stable backend metadata used by indexing and retrieval.
    """
    return EmbeddingBackendSpec(
        name=EMBEDDING_BACKEND,
        version=EMBEDDING_VERSION,
        dim=EMBEDDING_DIM,
    )


def _dependency_error(message: str) -> RuntimeError:
    """
    Build a stable runtime error for embedding backend provisioning failures.

    Parameters
    ----------
    message : str
        Specific failure reason to append.

    Returns
    -------
    RuntimeError
        Provisioning error with a repository-specific remediation hint.
    """
    return RuntimeError(
        "The semantic embedding backend requires the optional 'semantic' "
        "dependency set and a locally available model artifact for "
        f"{EMBEDDING_BACKEND}. {message}"
    )


@lru_cache(maxsize=1)
def _load_model() -> _EmbeddingModel:
    """
    Load the configured local sentence-transformers model.

    Parameters
    ----------
    None

    Returns
    -------
    object
        Loaded ``SentenceTransformer`` model instance cached for reuse.

    Raises
    ------
    RuntimeError
        Raised when the optional dependency or local model artifact is missing.
    """
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise _dependency_error(_DEPENDENCY_INSTALL_HINT) from exc

    try:
        from transformers.utils import logging as transformers_logging
    except ImportError:
        pass
    else:
        transformers_logging.set_verbosity_error()  # type: ignore[no-untyped-call]

    try:
        model = SentenceTransformer(EMBEDDING_BACKEND, device="cpu")
    except OSError as exc:
        raise _dependency_error(_MISSING_MODEL_HINT) from exc
    except RuntimeError as exc:
        raise _dependency_error(_MODEL_LOAD_HINT) from exc

    dimension = model.get_sentence_embedding_dimension()
    if dimension != EMBEDDING_DIM:
        msg = (
            "Loaded embedding model dimension "
            f"{dimension} does not match the repository contract {EMBEDDING_DIM}."
        )
        raise RuntimeError(msg)

    return cast("_EmbeddingModel", model)


def embed_text(text: str) -> list[float]:
    """
    Embed text using the deterministic local sentence-transformers backend.

    Parameters
    ----------
    text : str
        Text payload to embed.

    Returns
    -------
    list[float]
        L2-normalized embedding vector with fixed dimensionality.

    Raises
    ------
    RuntimeError
        Raised when the local semantic backend cannot be loaded.
    """
    if not text.strip():
        return [0.0] * EMBEDDING_DIM

    model = _load_model()
    vector = model.encode(
        [text],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]
    return [float(value) for value in vector.tolist()]


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
        Binary float32 representation of the vector.
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
