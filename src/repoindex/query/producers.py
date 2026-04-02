"""Shared query producer specifications for retrieval diagnostics.

Responsibilities
----------------
- Define stable query producer and channel spec dataclasses used by retrieval diagnostics.
- Centralize versioned producer metadata for channel and enrichment sources.
- Provide deterministic selection helpers for channel and enrichment producer specs.

Design principles
-----------------
Producer metadata stays explicit, immutable, and shared so query assembly does not duplicate versioning or capability declarations across modules.

Architectural role
------------------
This module belongs to the **query producer definition layer** that sits beside context assembly and exposes stable retrieval producer metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from repoindex.query.classifier import QueryIntent
    from repoindex.types import ChannelName, ChannelResults

from repoindex.contracts import RetrievalProducerInfo
from repoindex.registry import active_index_backend

QUERY_PRODUCER_VERSION = "1"
QUERY_CAPABILITY_VERSION = "1"
EnrichmentSourceName = Literal[
    "doc_issues",
    "call_graph",
    "references",
    "include_graph",
]


@dataclass(frozen=True)
class QueryProducerSpec:
    """
    Shared metadata describing one retrieval evidence source.

    Parameters
    ----------
    producer_name : str
        Stable producer identifier exposed in explain diagnostics.
    producer_version : str
        Producer implementation version.
    capability_version : str
        Version of the retrieval capability contract used for interpretation.
    capabilities : tuple[str, ...]
        Declared retrieval capabilities for the source.
    source_kind : {"channel", "enrichment"}
        Producer category.
    source_name : str
        Stable source identifier such as a channel or enrichment name.
    """

    producer_name: str
    producer_version: str
    capability_version: str
    capabilities: tuple[str, ...]
    source_kind: Literal["channel", "enrichment"]
    source_name: str


@dataclass(frozen=True)
class QueryChannelSpec:
    """
    Shared definition for one retrieval channel.

    Parameters
    ----------
    name : repoindex.types.ChannelName
        Stable channel name used by planning and explain output.
    retrieve : collections.abc.Callable[
        [pathlib.Path, str, sqlite3.Connection, QueryIntent, str | None],
        repoindex.types.ChannelResults,
    ]
        Retrieval function implementing the channel.
    producer : repoindex.query.producers.QueryProducerSpec
        Producer metadata associated with the channel.
    """

    name: ChannelName
    retrieve: Callable[
        [Path, str, sqlite3.Connection, QueryIntent, str | None],
        ChannelResults,
    ]
    producer: QueryProducerSpec


class EmbeddingRetrievalProducer(QueryProducerSpec):
    """
    Native retrieval producer for stored embedding similarity.

    Parameters
    ----------
    producer_name : str
        Stable producer identifier exposed in explain diagnostics.
    producer_version : str
        Producer implementation version.
    capability_version : str
        Version of the retrieval capability contract used for interpretation.
    capabilities : tuple[str, ...]
        Declared retrieval capabilities for the source.
    source_kind : {"channel", "enrichment"}
        Producer category.
    source_name : str
        Stable source identifier for the embedding channel.
    """

    def retrieval_producer_info(self) -> RetrievalProducerInfo:
        """
        Return versioned identity metadata for the embedding producer.

        Parameters
        ----------
        None

        Returns
        -------
        repoindex.contracts.RetrievalProducerInfo
            Producer identity and capability-version metadata.
        """
        return RetrievalProducerInfo(
            producer_name=self.producer_name,
            producer_version=self.producer_version,
            capability_version=self.capability_version,
        )

    def retrieval_capabilities(self) -> tuple[str, ...]:
        """
        Return declared retrieval capabilities for the embedding producer.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[str, ...]
            Declared capability names in deterministic order.
        """
        return self.capabilities

    def retrieve_candidates(  # noqa: PLR0913
        self,
        root: Path,
        query: str,
        *,
        limit: int,
        min_score: float,
        prefix: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> ChannelResults:
        """
        Retrieve ranked candidates using stored embedding similarity.

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
            Existing database connection to reuse.

        Returns
        -------
        repoindex.types.ChannelResults
            Ranked symbol candidates ordered by backend similarity semantics.
        """
        backend = active_index_backend()
        return backend.embedding_candidates(
            root,
            query,
            limit=limit,
            min_score=min_score,
            prefix=prefix,
            conn=conn,
        )


EMBEDDING_RETRIEVAL_PRODUCER = EmbeddingRetrievalProducer(
    producer_name="query-channel-embedding",
    producer_version=QUERY_PRODUCER_VERSION,
    capability_version=QUERY_CAPABILITY_VERSION,
    capabilities=("embedding_similarity", "diagnostics_metadata"),
    source_kind="channel",
    source_name="embedding",
)


CHANNEL_PRODUCER_SPECS: dict[ChannelName, QueryProducerSpec] = {
    "symbol": QueryProducerSpec(
        producer_name="query-channel-symbol",
        producer_version=QUERY_PRODUCER_VERSION,
        capability_version=QUERY_CAPABILITY_VERSION,
        capabilities=("symbol_lookup",),
        source_kind="channel",
        source_name="symbol",
    ),
    "embedding": EMBEDDING_RETRIEVAL_PRODUCER,
    "test": QueryProducerSpec(
        producer_name="query-channel-test",
        producer_version=QUERY_PRODUCER_VERSION,
        capability_version=QUERY_CAPABILITY_VERSION,
        capabilities=("symbol_lookup", "task_specialization"),
        source_kind="channel",
        source_name="test",
    ),
    "script": QueryProducerSpec(
        producer_name="query-channel-script",
        producer_version=QUERY_PRODUCER_VERSION,
        capability_version=QUERY_CAPABILITY_VERSION,
        capabilities=("symbol_lookup", "task_specialization"),
        source_kind="channel",
        source_name="script",
    ),
    "semantic": QueryProducerSpec(
        producer_name="query-channel-semantic",
        producer_version=QUERY_PRODUCER_VERSION,
        capability_version=QUERY_CAPABILITY_VERSION,
        capabilities=("semantic_text",),
        source_kind="channel",
        source_name="semantic",
    ),
}


ENRICHMENT_PRODUCER_SPECS: dict[EnrichmentSourceName, QueryProducerSpec] = {
    "doc_issues": QueryProducerSpec(
        producer_name="query-enrichment-doc-issues",
        producer_version=QUERY_PRODUCER_VERSION,
        capability_version=QUERY_CAPABILITY_VERSION,
        capabilities=("issue_annotations",),
        source_kind="enrichment",
        source_name="doc_issues",
    ),
    "call_graph": QueryProducerSpec(
        producer_name="query-enrichment-call-graph",
        producer_version=QUERY_PRODUCER_VERSION,
        capability_version=QUERY_CAPABILITY_VERSION,
        capabilities=("graph_relations",),
        source_kind="enrichment",
        source_name="call_graph",
    ),
    "references": QueryProducerSpec(
        producer_name="query-enrichment-references",
        producer_version=QUERY_PRODUCER_VERSION,
        capability_version=QUERY_CAPABILITY_VERSION,
        capabilities=("graph_relations",),
        source_kind="enrichment",
        source_name="references",
    ),
    "include_graph": QueryProducerSpec(
        producer_name="query-enrichment-include-graph",
        producer_version=QUERY_PRODUCER_VERSION,
        capability_version=QUERY_CAPABILITY_VERSION,
        capabilities=("graph_relations",),
        source_kind="enrichment",
        source_name="include_graph",
    ),
}


def channel_producer_specs(
    ordered_channels: Sequence[ChannelName],
) -> list[QueryProducerSpec]:
    """
    Return producer metadata for the supplied ordered channels.

    Parameters
    ----------
    ordered_channels : collections.abc.Sequence[repoindex.types.ChannelName]
        Channel order active for the query.

    Returns
    -------
    list[repoindex.query.producers.QueryProducerSpec]
        Channel producer specs in deterministic order.
    """

    return [
        CHANNEL_PRODUCER_SPECS[channel_name]
        for channel_name in ordered_channels
        if channel_name in CHANNEL_PRODUCER_SPECS
    ]


def selected_enrichment_producers(
    *,
    include_issue_annotations: bool,
    include_references: bool,
    include_include_graph: bool,
) -> list[QueryProducerSpec]:
    """
    Return enrichment producer metadata enabled for the current query.

    Parameters
    ----------
    include_issue_annotations : bool
        Whether doc-issue enrichment should be included.
    include_references : bool
        Whether callable-reference enrichment should be included.
    include_include_graph : bool
        Whether include-graph enrichment should be included.

    Returns
    -------
    list[repoindex.query.producers.QueryProducerSpec]
        Enrichment producer specs in deterministic evaluation order.
    """

    selected = [ENRICHMENT_PRODUCER_SPECS["call_graph"]]

    if include_issue_annotations:
        selected.insert(0, ENRICHMENT_PRODUCER_SPECS["doc_issues"])
    if include_references:
        selected.append(ENRICHMENT_PRODUCER_SPECS["references"])
    if include_include_graph:
        selected.append(ENRICHMENT_PRODUCER_SPECS["include_graph"])

    return selected
