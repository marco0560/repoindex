"""Core pluggable contracts introduced for ADR-004 Phase 3.

Responsibilities
----------------
- Define the `LanguageAnalyzer` and `IndexBackend` protocols that decouple parsing from persistence.
- Describe expectations for analyzer discovery, file support, and normalized `AnalysisResult` production.
- Specify backend responsibilities such as initialization, hash loading, deletion, and persistence operations.

Design principles
-----------------
Contracts stay explicit, minimal, and runtime-checkable so custom analyzers or backends can plug into the ADR-004 stack deterministically.

Architectural role
------------------
This module belongs to the **contract definition layer** that governs pluggable language analysis and storage backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from repoindex.models import AnalysisResult, FileMetadataSnapshot
    from repoindex.types import IncludeEdgeRow


@runtime_checkable
class LanguageAnalyzer(Protocol):
    """
    Contract for file analyzers participating in one indexing run.

    Implementations are responsible only for language-specific analysis and
    normalized artifact production. They must not own storage policy.
    """

    name: str
    version: str
    discovery_globs: tuple[str, ...]

    def supports_path(self, path: Path) -> bool:
        """
        Decide whether the analyzer can process a source path.

        Parameters
        ----------
        path : pathlib.Path
            Candidate repository file.

        Returns
        -------
        bool
            ``True`` when the analyzer accepts the file.
        """

    def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
        """
        Analyze one source file and emit normalized artifacts.

        Parameters
        ----------
        path : pathlib.Path
            Source file to analyze.
        root : pathlib.Path
            Repository root used for relative resolution.

        Returns
        -------
        repoindex.models.AnalysisResult
            Normalized artifacts for the file.
        """


RetrievalCapabilityName = Literal[
    "symbol_lookup",
    "semantic_text",
    "embedding_similarity",
    "task_specialization",
    "graph_relations",
    "issue_annotations",
    "diagnostics_metadata",
]

KNOWN_RETRIEVAL_CAPABILITIES: tuple[RetrievalCapabilityName, ...] = (
    "symbol_lookup",
    "semantic_text",
    "embedding_similarity",
    "task_specialization",
    "graph_relations",
    "issue_annotations",
    "diagnostics_metadata",
)


@dataclass(frozen=True)
class RetrievalProducerInfo:
    """
    Versioned identity for one retrieval-facing producer.

    Parameters
    ----------
    producer_name : str
        Stable producer identifier used in diagnostics and explain output.
    producer_version : str
        Producer implementation version.
    capability_version : str
        Version of the capability contract understood by the producer.
    """

    producer_name: str
    producer_version: str
    capability_version: str


@runtime_checkable
class RetrievalProducer(Protocol):
    """
    Contract for retrieval-facing producers that declare scoring capabilities.

    This protocol is layered beside ``LanguageAnalyzer`` so retrieval
    participation can evolve without overloading file-analysis contracts.
    """

    def retrieval_producer_info(self) -> RetrievalProducerInfo:
        """
        Return versioned identity metadata for one retrieval producer.

        Parameters
        ----------
        None

        Returns
        -------
        repoindex.contracts.RetrievalProducerInfo
            Producer identity and capability-version metadata.
        """

    def retrieval_capabilities(self) -> tuple[str, ...]:
        """
        Return declared retrieval capabilities for one producer.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[str, ...]
            Declared capability names in deterministic order.
        """


def split_declared_retrieval_capabilities(
    capabilities: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    Partition declared retrieval capabilities into known and unknown values.

    Parameters
    ----------
    capabilities : collections.abc.Sequence[str]
        Raw capability names declared by a retrieval producer.

    Returns
    -------
    tuple[tuple[str, ...], tuple[str, ...]]
        Known and unknown capability names in deterministic declaration order
        with duplicates removed.
    """
    known_set = set(KNOWN_RETRIEVAL_CAPABILITIES)
    seen: set[str] = set()
    known: list[str] = []
    unknown: list[str] = []

    for capability in capabilities:
        normalized = str(capability).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if normalized in known_set:
            known.append(normalized)
        else:
            unknown.append(normalized)

    return tuple(known), tuple(unknown)


@runtime_checkable
class IndexBackend(Protocol):
    """
    Contract for the single active persistence backend of one repository index.

    Backends own storage and query persistence concerns but must not perform
    language-specific parsing.
    """

    name: str
    version: str

    def initialize(self, root: Path) -> None:
        """
        Prepare persistent backend state for a repository root.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be prepared.

        Returns
        -------
        None
            Backend state is created or refreshed in place.
        """

    def load_existing_file_hashes(self, root: Path) -> dict[str, str]:
        """
        Load indexed file hashes used for incremental reuse decisions.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose backend state should be queried.

        Returns
        -------
        dict[str, str]
            Indexed file hashes keyed by absolute file path.
        """

    def delete_paths(self, root: Path, *, paths: Sequence[str]) -> None:
        """
        Remove persisted artifacts owned by the supplied file paths.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose backend state should be updated.
        paths : collections.abc.Sequence[str]
            Absolute file paths to remove from backend state.

        Returns
        -------
        None
            Matching persisted artifacts are removed in place.
        """

    def persist_analysis(
        self,
        root: Path,
        *,
        file_metadata: FileMetadataSnapshot,
        analysis: AnalysisResult,
    ) -> tuple[int, int]:
        """
        Persist normalized artifacts for one analyzed file snapshot.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose backend state should be updated.
        file_metadata : repoindex.models.FileMetadataSnapshot
            Stable file metadata captured during scanning.
        analysis : repoindex.models.AnalysisResult
            Normalized analyzer output for the file.

        Returns
        -------
        tuple[int, int]
            ``(recomputed, reused)`` semantic-artifact counts for the file.
        """

    def count_reusable_embeddings(self, root: Path, *, paths: Sequence[str]) -> int:
        """
        Count semantic artifacts that remain reusable for unchanged files.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose backend state should be queried.
        paths : collections.abc.Sequence[str]
            Absolute file paths considered reusable.

        Returns
        -------
        int
            Number of reusable semantic artifacts retained by the backend.
        """

    def rebuild_derived_indexes(self, root: Path) -> None:
        """
        Rebuild derived backend state after raw artifact persistence.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose backend state should be finalized.

        Returns
        -------
        None
            Derived backend indexes are refreshed in place.
        """

    def find_include_edges(
        self,
        root: Path,
        name: str,
        *,
        module: str | None = None,
        incoming: bool = False,
        prefix: str | None = None,
        conn: object | None = None,
    ) -> list[IncludeEdgeRow]:
        """
        Find exact include-like edges for an owner module or included target.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        name : str
            Exact owner module name or include target path to search for.
        module : str | None, optional
            Optional owner-module qualifier used to restrict incoming results.
        incoming : bool, optional
            Whether to return incoming edges for the included target.
        prefix : str | None, optional
            Repo-root-relative path prefix used to restrict owner files.
        conn : object | None, optional
            Existing backend connection to reuse.

        Returns
        -------
        list[repoindex.types.IncludeEdgeRow]
            Matching include-edge rows ordered deterministically as
            ``(owner_module, target_name, kind, lineno)`` tuples.
        """
