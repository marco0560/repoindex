"""Deterministic local embedding backend for repoindex."""

from __future__ import annotations

import contextlib
import io
import os
import struct
import sys
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

    class _SentenceTransformerFactory(Protocol):
        def __call__(
            self,
            model_name: str,
            *,
            device: str,
            local_files_only: bool,
        ) -> _EmbeddingModel: ...


EMBEDDING_BACKEND = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_VERSION = "1"
EMBEDDING_DIM = 384
_DEPENDENCY_INSTALL_HINT = (
    "Install repoindex with the 'semantic' or 'firstparty' extra. "
    "For editable installs from another repository, use "
    "'pip install -e ../repoindex[firstparty]'."
)


class EmbeddingBackendError(RuntimeError):
    """
    Stable operator-facing error raised by the embedding backend.

    Parameters
    ----------
    message : str
        Human-readable provisioning or dependency error.
    """


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


def _dependency_error(message: str) -> EmbeddingBackendError:
    """
    Build a stable runtime error for embedding backend provisioning failures.

    Parameters
    ----------
    message : str
        Specific failure reason to append.

    Returns
    -------
    EmbeddingBackendError
        Provisioning error with a repository-specific remediation hint.
    """
    return EmbeddingBackendError(
        "The semantic embedding backend requires the optional 'semantic' "
        "dependency set and a locally available model artifact for "
        f"{EMBEDDING_BACKEND}. {message}"
    )


def _wrap_load_error(exc: OSError | RuntimeError) -> EmbeddingBackendError:
    """
    Convert low-level model-loading failures into a stable operator error.

    Parameters
    ----------
    exc : OSError | RuntimeError
        Original model-loading exception.

    Returns
    -------
    EmbeddingBackendError
        Concise error suitable for CLI reporting.
    """
    return _dependency_error(
        "Automatic model provisioning failed. "
        "Check network access or prefetch the artifact with "
        "'python ../repoindex/scripts/provision_embedding_model.py'. "
        f"Loader details: {exc}"
    )


def _configure_embedding_environment(*, offline: bool) -> None:
    """
    Configure process-local environment variables for model loading.

    Parameters
    ----------
    offline : bool
        Whether model loading should require local artifacts only.

    Returns
    -------
    None
        Environment variables are updated in place for the current process.
    """
    os.environ["HF_HUB_OFFLINE"] = "1" if offline else "0"
    os.environ["TRANSFORMERS_OFFLINE"] = "1" if offline else "0"
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def _load_sentence_transformer(
    sentence_transformer: object,
    *,
    offline: bool,
) -> _EmbeddingModel:
    """
    Load the configured model with optional offline-only behavior.

    Parameters
    ----------
    sentence_transformer : object
        Imported ``SentenceTransformer`` constructor or compatible callable.
    offline : bool
        Whether model loading should require a local artifact.

    Returns
    -------
    _EmbeddingModel
        Loaded embedding model instance.
    """
    _configure_embedding_environment(offline=offline)
    factory = cast("_SentenceTransformerFactory", sentence_transformer)
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return factory(
            EMBEDDING_BACKEND,
            device="cpu",
            local_files_only=offline,
        )


def provision_embedding_model(*, quiet: bool = False) -> None:
    """
    Ensure the configured local embedding model artifact is available.

    Parameters
    ----------
    quiet : bool, optional
        Whether to suppress the operator-facing provisioning message.

    Returns
    -------
    None
        The model artifact is downloaded or verified in the local cache.

    Raises
    ------
    EmbeddingBackendError
        Raised when the semantic dependency stack is missing or the model
        artifact cannot be provisioned.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise _dependency_error(_DEPENDENCY_INSTALL_HINT) from exc

    if not quiet:
        print(
            "[repoindex] Provisioning local embedding model " f"{EMBEDDING_BACKEND}...",
            file=sys.stderr,
        )

    try:
        _load_sentence_transformer(SentenceTransformer, offline=False)
    except (OSError, RuntimeError) as exc:
        raise _wrap_load_error(exc) from exc


@lru_cache(maxsize=1)
def _load_model() -> _EmbeddingModel:
    """
    Load the configured local sentence-transformers model.

    Parameters
    ----------
    None

    Returns
    -------
    _EmbeddingModel
        Loaded ``SentenceTransformer`` model instance cached for reuse.

    Raises
    ------
    EmbeddingBackendError
        Raised when the optional dependency or local model artifact is missing.
    """
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
        model = _load_sentence_transformer(SentenceTransformer, offline=True)
    except OSError:
        provision_embedding_model()
        try:
            model = _load_sentence_transformer(SentenceTransformer, offline=True)
        except (OSError, RuntimeError) as exc:
            raise _wrap_load_error(exc) from exc
    except RuntimeError as exc:
        raise _wrap_load_error(exc) from exc

    dimension = model.get_sentence_embedding_dimension()
    if dimension != EMBEDDING_DIM:
        msg = (
            "Loaded embedding model dimension "
            f"{dimension} does not match the repository contract {EMBEDDING_DIM}."
        )
        raise EmbeddingBackendError(msg)

    return model


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
    EmbeddingBackendError
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
