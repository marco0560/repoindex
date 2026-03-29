"""Backend and analyzer registries for ADR-004 Phase 8."""

from __future__ import annotations

import importlib
import importlib.metadata as metadata
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from repoindex.contracts import IndexBackend, LanguageAnalyzer

if TYPE_CHECKING:
    from repoindex.indexer import SQLiteIndexBackend

DEFAULT_INDEX_BACKEND = "sqlite"
INDEX_BACKEND_ENV_VAR = "REPOINDEX_INDEX_BACKEND"
ANALYZER_ENTRY_POINT_GROUP = "repoindex.analyzers"
BACKEND_ENTRY_POINT_GROUP = "repoindex.backends"
OPTIONAL_ANALYZER_EXTRA_BY_NAME: dict[str, str] = {"c": "repoindex[c]"}
OPTIONAL_ANALYZER_DEPENDENCY_NAMES: dict[str, set[str]] = {
    "c": {"tree_sitter", "tree_sitter_c"},
}
REQUIRED_BACKEND_METHODS: tuple[str, ...] = (
    "open_connection",
    "initialize",
    "load_existing_file_hashes",
    "delete_paths",
    "persist_analysis",
    "count_reusable_embeddings",
    "rebuild_derived_indexes",
    "list_symbols_in_module",
    "find_symbol",
    "docstring_issues",
    "find_call_edges",
    "find_callable_refs",
    "find_include_edges",
    "find_logical_symbols",
    "logical_symbol_name",
    "embedding_inventory",
    "embedding_candidates",
    "prune_orphaned_embeddings",
    "current_embedding_state_matches",
)
PluginFamily = Literal["analyzer", "backend"]
PluginSource = Literal["builtin", "entry_point"]
PluginStatus = Literal["loaded", "skipped", "duplicate"]


@dataclass(frozen=True)
class PluginRegistration:
    """
    Deterministic plugin registration record.

    Parameters
    ----------
    family : {"analyzer", "backend"}
        Plugin extension family.
    name : str
        Stable analyzer or backend name.
    provider : str
        Distribution or built-in provider label.
    source : {"builtin", "entry_point"}
        Registration source.
    status : {"loaded", "skipped", "duplicate"}
        Registration outcome used by diagnostics and CLI reporting.
    version : str
        Plugin implementation version string.
    entry_point : str | None, optional
        Entry-point name for third-party plugins.
    detail : str | None, optional
        Deterministic explanation for skipped or duplicate records.
    """

    family: PluginFamily
    name: str
    provider: str
    source: PluginSource
    status: PluginStatus
    version: str
    entry_point: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class _LoadedPlugin:
    """
    Internal loaded-plugin representation used by registry resolution.

    Parameters
    ----------
    family : {"analyzer", "backend"}
        Plugin extension family.
    name : str
        Stable analyzer or backend name.
    provider : str
        Distribution or built-in provider label.
    source : {"builtin", "entry_point"}
        Registration source.
    version : str
        Plugin implementation version string.
    factory : collections.abc.Callable[[], object]
        Zero-argument factory producing the plugin implementation.
    entry_point : str | None, optional
        Entry-point name for third-party plugins.
    """

    family: PluginFamily
    name: str
    provider: str
    source: PluginSource
    version: str
    factory: Callable[[], object]
    entry_point: str | None = None


def _registered_index_backends() -> dict[str, type[SQLiteIndexBackend]]:
    """
    Return the backend factory registry keyed by backend name.

    Parameters
    ----------
    None

    Returns
    -------
    dict[str, type[repoindex.indexer.SQLiteIndexBackend]]
        Deterministic backend factories keyed by stable backend name.
    """
    from repoindex.indexer import SQLiteIndexBackend

    return {"sqlite": SQLiteIndexBackend}


def _builtin_backend_plugins() -> list[_LoadedPlugin]:
    """
    Return built-in backend registrations.

    Parameters
    ----------
    None

    Returns
    -------
    list[repoindex.registry._LoadedPlugin]
        Built-in backend plugins in deterministic order.
    """
    backends = _registered_index_backends()
    loaded: list[_LoadedPlugin] = []

    for name in sorted(backends):
        factory = backends[name]
        instance = factory()
        loaded.append(
            _LoadedPlugin(
                family="backend",
                name=name,
                provider="repoindex",
                source="builtin",
                version=str(instance.version),
                factory=factory,
            )
        )

    return loaded


def _registered_language_analyzer_factories() -> (
    tuple[Callable[[], LanguageAnalyzer], ...]
):
    """
    Return the registered language analyzer factories in routing order.

    Parameters
    ----------
    None

    Returns
    -------
    tuple[collections.abc.Callable[[], repoindex.contracts.LanguageAnalyzer], ...]
        Analyzer factories in deterministic first-match order.
    """
    from repoindex.analyzers.python import PythonAnalyzer

    factories: list[Callable[[], LanguageAnalyzer]] = [
        cast(Callable[[], LanguageAnalyzer], PythonAnalyzer)
    ]
    c_factory = _optional_language_analyzer_factory(
        "repoindex.analyzers.c",
        "CAnalyzer",
        analyzer_name="c",
    )
    if c_factory is not None:
        factories.append(c_factory)
    return tuple(factories)


def _builtin_analyzer_plugins() -> list[_LoadedPlugin]:
    """
    Return built-in analyzer registrations.

    Parameters
    ----------
    None

    Returns
    -------
    list[repoindex.registry._LoadedPlugin]
        Built-in analyzer plugins in deterministic routing order.
    """
    factories = _registered_language_analyzer_factories()
    loaded: list[_LoadedPlugin] = []

    for factory in factories:
        instance = factory()
        loaded.append(
            _LoadedPlugin(
                family="analyzer",
                name=str(instance.name),
                provider="repoindex",
                source="builtin",
                version=str(instance.version),
                factory=factory,
            )
        )

    return loaded


def _optional_language_analyzer_factory(
    module_name: str,
    class_name: str,
    *,
    analyzer_name: str,
) -> Callable[[], LanguageAnalyzer] | None:
    """
    Load one optional analyzer factory when its dependencies are installed.

    Parameters
    ----------
    module_name : str
        Fully qualified analyzer module path.
    class_name : str
        Analyzer class name exported by the module.
    analyzer_name : str
        Stable analyzer registry name.

    Returns
    -------
    collections.abc.Callable[[], repoindex.contracts.LanguageAnalyzer] | None
        Analyzer factory when optional dependencies are available, otherwise
        ``None``.

    Raises
    ------
    ModuleNotFoundError
        If the analyzer module fails for reasons unrelated to its documented
        optional dependencies.
    """
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        optional_dependencies = OPTIONAL_ANALYZER_DEPENDENCY_NAMES.get(
            analyzer_name,
            set(),
        )
        if exc.name in optional_dependencies:
            return None
        raise

    factory = cast(Callable[[], LanguageAnalyzer], getattr(module, class_name))
    return factory


def _entry_points_for_group(group: str) -> list[metadata.EntryPoint]:
    """
    Return entry points for one plugin group in deterministic order.

    Parameters
    ----------
    group : str
        Entry-point group name.

    Returns
    -------
    list[importlib.metadata.EntryPoint]
        Entry points sorted by provider and entry-point name.
    """
    discovered = list(metadata.entry_points(group=group))
    discovered.sort(
        key=lambda entry: (
            getattr(getattr(entry, "dist", None), "name", "") or "",
            entry.name,
            entry.value,
        )
    )
    return discovered


def _load_entry_point_plugin(
    entry_point: metadata.EntryPoint,
    *,
    family: PluginFamily,
) -> tuple[_LoadedPlugin | None, PluginRegistration]:
    """
    Load one entry-point plugin and validate its contract.

    Parameters
    ----------
    entry_point : importlib.metadata.EntryPoint
        Entry point to resolve.
    family : {"analyzer", "backend"}
        Expected plugin family for contract validation.

    Returns
    -------
    tuple[
        repoindex.registry._LoadedPlugin | None,
        repoindex.registry.PluginRegistration,
    ]
        Loaded plugin and its registration record. Failed loads return
        ``None`` plus a skipped registration record.
    """
    provider = getattr(getattr(entry_point, "dist", None), "name", "") or "<unknown>"

    try:
        loaded_object = entry_point.load()
    except Exception as exc:
        return None, PluginRegistration(
            family=family,
            name=entry_point.name,
            provider=provider,
            source="entry_point",
            status="skipped",
            version="unknown",
            entry_point=entry_point.name,
            detail=f"load failed: {exc.__class__.__name__}: {exc}",
        )

    if not callable(loaded_object):
        return None, PluginRegistration(
            family=family,
            name=entry_point.name,
            provider=provider,
            source="entry_point",
            status="skipped",
            version="unknown",
            entry_point=entry_point.name,
            detail="entry point is not callable",
        )

    factory = cast(Callable[[], object], loaded_object)

    try:
        instance = factory()
    except Exception as exc:
        return None, PluginRegistration(
            family=family,
            name=entry_point.name,
            provider=provider,
            source="entry_point",
            status="skipped",
            version="unknown",
            entry_point=entry_point.name,
            detail=f"factory failed: {exc.__class__.__name__}: {exc}",
        )

    if family == "analyzer":
        if not isinstance(instance, LanguageAnalyzer):
            return None, PluginRegistration(
                family=family,
                name=entry_point.name,
                provider=provider,
                source="entry_point",
                status="skipped",
                version="unknown",
                entry_point=entry_point.name,
                detail="factory returned a non-LanguageAnalyzer object",
            )
        discovery_globs = getattr(instance, "discovery_globs", None)
        invalid_discovery_globs = (
            not isinstance(discovery_globs, tuple)
            or not discovery_globs
            or any(
                not isinstance(pattern, str) or not pattern.strip()
                for pattern in discovery_globs
            )
        )
        if invalid_discovery_globs:
            return None, PluginRegistration(
                family=family,
                name=entry_point.name,
                provider=provider,
                source="entry_point",
                status="skipped",
                version="unknown",
                entry_point=entry_point.name,
                detail="analyzer discovery_globs must be a non-empty tuple[str, ...]",
            )
    else:
        if not isinstance(instance, IndexBackend):
            return None, PluginRegistration(
                family=family,
                name=entry_point.name,
                provider=provider,
                source="entry_point",
                status="skipped",
                version="unknown",
                entry_point=entry_point.name,
                detail="factory returned a non-IndexBackend object",
            )
        missing_methods = [
            method
            for method in REQUIRED_BACKEND_METHODS
            if not callable(getattr(instance, method, None))
        ]
        if missing_methods:
            joined = ", ".join(sorted(missing_methods))
            return None, PluginRegistration(
                family=family,
                name=entry_point.name,
                provider=provider,
                source="entry_point",
                status="skipped",
                version="unknown",
                entry_point=entry_point.name,
                detail=f"backend is missing required methods: {joined}",
            )

    name = getattr(instance, "name", None)
    raw_version = getattr(instance, "version", None)
    if not isinstance(name, str) or not name.strip():
        return None, PluginRegistration(
            family=family,
            name=entry_point.name,
            provider=provider,
            source="entry_point",
            status="skipped",
            version="unknown",
            entry_point=entry_point.name,
            detail="plugin name must be a non-empty string",
        )
    version = None if raw_version is None else str(raw_version).strip()
    if not version:
        return None, PluginRegistration(
            family=family,
            name=name,
            provider=provider,
            source="entry_point",
            status="skipped",
            version="unknown",
            entry_point=entry_point.name,
            detail="plugin version must be a non-empty string",
        )

    return (
        _LoadedPlugin(
            family=family,
            name=name,
            provider=provider,
            source="entry_point",
            version=version,
            factory=factory,
            entry_point=entry_point.name,
        ),
        PluginRegistration(
            family=family,
            name=name,
            provider=provider,
            source="entry_point",
            status="loaded",
            version=version,
            entry_point=entry_point.name,
        ),
    )


def _discover_entry_point_plugins(
    *,
    family: PluginFamily,
    group: str,
) -> tuple[list[_LoadedPlugin], list[PluginRegistration]]:
    """
    Discover entry-point plugins for one extension family.

    Parameters
    ----------
    family : {"analyzer", "backend"}
        Plugin extension family.
    group : str
        Entry-point group to inspect.

    Returns
    -------
    tuple[
        list[repoindex.registry._LoadedPlugin],
        list[repoindex.registry.PluginRegistration],
    ]
        Loaded plugins plus diagnostic registration records.
    """
    loaded: list[_LoadedPlugin] = []
    registrations: list[PluginRegistration] = []

    for entry_point in _entry_points_for_group(group):
        plugin, registration = _load_entry_point_plugin(entry_point, family=family)
        registrations.append(registration)
        if plugin is not None:
            loaded.append(plugin)

    return loaded, registrations


def _resolve_plugins(
    builtins: list[_LoadedPlugin],
    externals: list[_LoadedPlugin],
    external_registrations: list[PluginRegistration],
) -> tuple[list[_LoadedPlugin], list[PluginRegistration]]:
    """
    Merge built-in and entry-point plugins with duplicate rejection.

    Parameters
    ----------
    builtins : list[repoindex.registry._LoadedPlugin]
        Built-in plugin registrations.
    externals : list[repoindex.registry._LoadedPlugin]
        Successfully loaded entry-point plugins.
    external_registrations : list[repoindex.registry.PluginRegistration]
        Entry-point registration diagnostics.

    Returns
    -------
    tuple[
        list[repoindex.registry._LoadedPlugin],
        list[repoindex.registry.PluginRegistration],
    ]
        Loaded plugins that survived duplicate checks plus full diagnostics.
    """
    resolved = list(builtins)
    registrations = [
        PluginRegistration(
            family=plugin.family,
            name=plugin.name,
            provider=plugin.provider,
            source=plugin.source,
            status="loaded",
            version=plugin.version,
            entry_point=plugin.entry_point,
        )
        for plugin in builtins
    ]
    seen_names = {plugin.name for plugin in builtins}

    duplicate_keys: set[tuple[str, str, str]] = set()

    for plugin in externals:
        if plugin.name in seen_names:
            duplicate_keys.add(
                (
                    plugin.provider,
                    plugin.entry_point or "",
                    plugin.name,
                )
            )
            registrations.append(
                PluginRegistration(
                    family=plugin.family,
                    name=plugin.name,
                    provider=plugin.provider,
                    source=plugin.source,
                    status="duplicate",
                    version=plugin.version,
                    entry_point=plugin.entry_point,
                    detail="duplicate plugin name rejected",
                )
            )
            continue
        seen_names.add(plugin.name)
        resolved.append(plugin)

    for registration in external_registrations:
        key = (
            registration.provider,
            registration.entry_point or "",
            registration.name,
        )
        if registration.status == "loaded" and key in duplicate_keys:
            continue
        registrations.append(registration)
    return resolved, registrations


def _plugin_snapshot(
    family: PluginFamily,
) -> tuple[list[_LoadedPlugin], list[PluginRegistration]]:
    """
    Build the registry snapshot for one plugin family.

    Parameters
    ----------
    family : {"analyzer", "backend"}
        Plugin extension family.

    Returns
    -------
    tuple[
        list[repoindex.registry._LoadedPlugin],
        list[repoindex.registry.PluginRegistration],
    ]
        Resolved plugins plus diagnostic registrations.
    """
    if family == "analyzer":
        builtins = _builtin_analyzer_plugins()
        externals, external_registrations = _discover_entry_point_plugins(
            family="analyzer",
            group=ANALYZER_ENTRY_POINT_GROUP,
        )
    else:
        builtins = _builtin_backend_plugins()
        externals, external_registrations = _discover_entry_point_plugins(
            family="backend",
            group=BACKEND_ENTRY_POINT_GROUP,
        )

    return _resolve_plugins(builtins, externals, external_registrations)


def plugin_registrations() -> list[PluginRegistration]:
    """
    Return deterministic plugin registration diagnostics.

    Parameters
    ----------
    None

    Returns
    -------
    list[repoindex.registry.PluginRegistration]
        Built-in and external plugin registrations for analyzers and backends.
    """
    analyzer_plugins, analyzer_registrations = _plugin_snapshot("analyzer")
    backend_plugins, backend_registrations = _plugin_snapshot("backend")
    del analyzer_plugins, backend_plugins
    return analyzer_registrations + backend_registrations


def missing_language_analyzer_hint(path: Path) -> str | None:
    """
    Return an installation hint when a path targets an unavailable analyzer.

    Parameters
    ----------
    path : pathlib.Path
        Repository file whose suffix can imply an optional analyzer.

    Returns
    -------
    str | None
        Deterministic installation hint, or ``None`` when no optional analyzer
        applies.
    """
    suffix = path.suffix.lower()

    if (
        suffix in {".c", ".h"}
        and _optional_language_analyzer_factory(
            "repoindex.analyzers.c",
            "CAnalyzer",
            analyzer_name="c",
        )
        is None
    ):
        extra = OPTIONAL_ANALYZER_EXTRA_BY_NAME["c"]
        return (
            "C-family indexing support is optional. "
            f"Install the extra with `{extra}` to enable `*.c` and `*.h` files."
        )

    return None


def configured_index_backend_name() -> str:
    """
    Return the configured backend name for the current process.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Configured backend name, defaulting to ``"sqlite"``.
    """
    configured_name = os.getenv(INDEX_BACKEND_ENV_VAR, DEFAULT_INDEX_BACKEND).strip()
    if configured_name:
        return configured_name
    return DEFAULT_INDEX_BACKEND


def active_index_backend() -> SQLiteIndexBackend:
    """
    Instantiate the configured index backend.

    Parameters
    ----------
    None

    Returns
    -------
    repoindex.indexer.SQLiteIndexBackend
        Active backend implementation for indexing and querying.

    Raises
    ------
    ValueError
        If the configured backend name is not registered.
    """
    from repoindex.indexer import SQLiteIndexBackend

    configured_name = configured_index_backend_name()
    plugins, _registrations = _plugin_snapshot("backend")
    registry = {
        plugin.name: cast(type[SQLiteIndexBackend], plugin.factory)
        for plugin in plugins
    }
    factory = registry.get(configured_name)

    if factory is None:
        available = ", ".join(sorted(registry))
        msg = (
            f"Unsupported repoindex backend '{configured_name}'. "
            f"Available backends: {available}"
        )
        raise ValueError(msg)

    return factory()


def _instantiate_language_analyzers(
    analyzer_factories: Sequence[Callable[[], LanguageAnalyzer]],
) -> list[LanguageAnalyzer]:
    """
    Instantiate registered analyzers in deterministic routing order.

    Parameters
    ----------
    analyzer_factories : collections.abc.Sequence[Callable[[], LanguageAnalyzer]]
        Analyzer factories in deterministic routing order.

    Returns
    -------
    list[repoindex.contracts.LanguageAnalyzer]
        Instantiated analyzers in the same order as the supplied factories.

    Raises
    ------
    ValueError
        If no analyzers are registered.
    """
    analyzers = [factory() for factory in analyzer_factories]
    if analyzers:
        return analyzers

    msg = "No language analyzers are registered for repoindex"
    raise ValueError(msg)


def active_language_analyzers() -> list[LanguageAnalyzer]:
    """
    Instantiate the active language analyzers for one indexing run.

    Parameters
    ----------
    None

    Returns
    -------
    list[repoindex.contracts.LanguageAnalyzer]
        Active analyzers in deterministic first-match routing order.
    """
    plugins, _registrations = _plugin_snapshot("analyzer")
    factories = [
        cast(Callable[[], LanguageAnalyzer], plugin.factory) for plugin in plugins
    ]
    return _instantiate_language_analyzers(factories)
