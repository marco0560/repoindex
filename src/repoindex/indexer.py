"""Index repository symbols and docstring diagnostics into SQLite."""

from __future__ import annotations

import json
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from repoindex.docstring import validate_docstring
from repoindex.models import (
    AnalysisResult,
    CallableReference,
    CallSite,
    FileMetadataSnapshot,
    FunctionArtifact,
)
from repoindex.prefix import normalize_prefix, prefix_clause
from repoindex.registry import (
    active_index_backend,
    active_language_analyzers,
    missing_language_analyzer_hint,
)
from repoindex.scanner import (
    CANONICAL_SOURCE_DIRS,
    file_metadata,
    iter_canonical_project_files,
    iter_project_files,
)
from repoindex.schema import SCHEMA_VERSION
from repoindex.semantic.embeddings import (
    EmbeddingBackendSpec,
    deserialize_vector,
    embed_text,
    get_embedding_backend,
    serialize_vector,
)
from repoindex.storage import get_db_path, init_db

if TYPE_CHECKING:
    from repoindex.contracts import LanguageAnalyzer
    from repoindex.types import ChannelResults, IncludeEdgeRow, SymbolRow

CallRecord = dict[str, str | int]
ReferenceRecord = dict[str, str | int]
ParsedFile = tuple[Path, FileMetadataSnapshot, AnalysisResult]
CallEdgeRow = tuple[str, str, str | None, str | None, int]
CallableRefRow = tuple[str, str, str | None, str | None, int]
EmbeddingInventoryRow = tuple[str, str, int, int]
_IGNORED_COVERAGE_SUFFIXES = frozenset({"<no-suffix>", ".md", ".txt"})
_BINARY_SNIFF_BYTES = 8192


@dataclass(frozen=True)
class IndexDecision:
    """
    Deterministic per-file indexing decision.

    Parameters
    ----------
    path : str
        Absolute file path considered by the indexer.
    action : str
        Decision category such as ``indexed``, ``reused``, or ``deleted``.
    reason : str
        Stable explanation for the decision.
    """

    path: str
    action: str
    reason: str


@dataclass(frozen=True)
class CoverageIssue:
    """
    Deterministic canonical-directory coverage gap.

    Parameters
    ----------
    path : str
        Absolute path to the uncovered file.
    directory : str
        Canonical top-level directory containing the file.
    suffix : str
        File suffix reported for grouping and diagnostics.
    reason : str
        Stable explanation for why the file is uncovered.
    """

    path: str
    directory: str
    suffix: str
    reason: str


@dataclass(frozen=True)
class IndexFailure:
    """
    Deterministic per-file indexing failure diagnostic.

    Parameters
    ----------
    path : str
        Absolute path to the file that could not be indexed.
    analyzer_name : str
        Analyzer selected for the file.
    error_type : str
        Exception class name raised during analysis.
    reason : str
        Stable human-readable failure summary.
    """

    path: str
    analyzer_name: str
    error_type: str
    reason: str


@dataclass(frozen=True)
class IndexWarning:
    """
    Deterministic per-file indexing warning diagnostic.

    Parameters
    ----------
    path : str
        Absolute path to the file that emitted the warning.
    analyzer_name : str
        Analyzer selected for the file.
    warning_type : str
        Warning category class name raised during analysis.
    line : int | None
        Source line associated with the warning when available.
    reason : str
        Stable human-readable warning summary.
    """

    path: str
    analyzer_name: str
    warning_type: str
    line: int | None
    reason: str


@dataclass(frozen=True)
class IndexReport:
    """
    Summary of one indexing run.

    Parameters
    ----------
    indexed : int
        Number of files reparsed and successfully reindexed.
    reused : int
        Number of files reused without reparsing.
    deleted : int
        Number of deleted files removed from the index.
    failed : int
        Number of files skipped because analysis failed.
    embeddings_recomputed : int
        Number of embeddings written during the run.
    embeddings_reused : int
        Number of existing embeddings preserved for unchanged files.
    decisions : list[IndexDecision]
        Deterministic per-file decisions for explain mode.
    failures : list[IndexFailure]
        Deterministic per-file analysis failures recorded during the run.
    warnings : list[IndexWarning]
        Deterministic per-file analysis warnings recorded during the run.
    coverage_issues : list[CoverageIssue]
        Uncovered canonical-directory files detected during the run.
    """

    indexed: int
    reused: int
    deleted: int
    failed: int
    embeddings_recomputed: int
    embeddings_reused: int
    decisions: list[IndexDecision]
    failures: list[IndexFailure]
    warnings: list[IndexWarning]
    coverage_issues: list[CoverageIssue]


@dataclass(frozen=True)
class ProjectScanState:
    """
    Current repository scan state used for incremental planning.

    Parameters
    ----------
    analyzers_by_path : dict[str, repoindex.contracts.LanguageAnalyzer]
        Active analyzer selected for each tracked project file.
    metadata_by_path : dict[str, dict[str, object]]
        Current raw file metadata snapshots keyed by absolute path.
    paths : list[str]
        Deterministically ordered tracked project paths.
    """

    analyzers_by_path: dict[str, LanguageAnalyzer]
    metadata_by_path: dict[str, dict[str, object]]
    paths: list[str]


@dataclass(frozen=True)
class ExistingIndexState:
    """
    Persisted index state used to determine reuse decisions.

    Parameters
    ----------
    file_hashes : dict[str, str]
        Indexed content hashes keyed by absolute file path.
    file_ownership : dict[str, tuple[str, str]]
        Persisted analyzer ownership keyed by absolute file path.
    paths : list[str]
        Deterministically ordered indexed file paths.
    embedding_backend_matches : bool
        Whether persisted embeddings match the active embedding backend.
    """

    file_hashes: dict[str, str]
    file_ownership: dict[str, tuple[str, str]]
    paths: list[str]
    embedding_backend_matches: bool


@dataclass(frozen=True)
class IndexPlan:
    """
    Deterministic plan for one indexing pass.

    Parameters
    ----------
    indexed_paths : list[str]
        Files that must be reparsed and persisted.
    reused_paths : list[str]
        Files whose persisted data can be reused unchanged.
    deleted_paths : list[str]
        Files to remove from the persisted index.
    decisions : list[IndexDecision]
        Per-file explanations for indexed, reused, and deleted outcomes.
    """

    indexed_paths: list[str]
    reused_paths: list[str]
    deleted_paths: list[str]
    decisions: list[IndexDecision]


def _is_binary_coverage_candidate(path: Path) -> bool:
    """
    Return whether a coverage candidate should be treated as binary.

    Parameters
    ----------
    path : pathlib.Path
        Repository file to inspect conservatively.

    Returns
    -------
    bool
        ``True`` when the initial file chunk contains a NUL byte, which is
        sufficient for repoindex coverage suppression of obvious binary files.
    """
    with path.open("rb") as handle:
        return b"\x00" in handle.read(_BINARY_SNIFF_BYTES)


def _should_ignore_coverage_gap(path: Path) -> bool:
    """
    Return whether an uncovered canonical file should be excluded from coverage.

    Parameters
    ----------
    path : pathlib.Path
        Repository file that no analyzer claimed.

    Returns
    -------
    bool
        ``True`` when the file belongs to a deliberately ignored suffix class
        or is conservatively identified as binary content.
    """
    suffix = path.suffix.lower() or "<no-suffix>"
    if suffix in _IGNORED_COVERAGE_SUFFIXES:
        return True
    return _is_binary_coverage_candidate(path)


def _audit_canonical_directory_coverage(
    root: Path,
    *,
    analyzers: list[LanguageAnalyzer],
) -> list[CoverageIssue]:
    """
    Audit canonical source directories for uncovered tracked files.

    Parameters
    ----------
    root : pathlib.Path
        Repository root being indexed.
    analyzers : list[repoindex.contracts.LanguageAnalyzer]
        Active analyzers available for file routing.

    Returns
    -------
    list[CoverageIssue]
        Deterministic uncovered-file diagnostics for canonical directories.
    """
    issues: list[CoverageIssue] = []

    for path in iter_canonical_project_files(root):
        if any(analyzer.supports_path(path) for analyzer in analyzers):
            continue
        rel_path = path.relative_to(root)
        top_dir = rel_path.parts[0] if rel_path.parts else ""
        if top_dir not in CANONICAL_SOURCE_DIRS:
            continue
        if _should_ignore_coverage_gap(path):
            continue
        suffix = path.suffix.lower() or "<no-suffix>"
        issues.append(
            CoverageIssue(
                path=str(path),
                directory=top_dir,
                suffix=suffix,
                reason="no registered analyzer covers this canonical file",
            )
        )

    issues.sort(
        key=lambda issue: (
            issue.directory,
            issue.suffix,
            issue.path,
        )
    )
    return issues


def audit_repo_coverage(root: Path) -> list[CoverageIssue]:
    """
    Audit canonical-directory coverage for the active analyzer environment.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose tracked canonical files should be checked.

    Returns
    -------
    list[CoverageIssue]
        Deterministic uncovered-file diagnostics for the current analyzer set.
    """
    return _audit_canonical_directory_coverage(
        root,
        analyzers=_active_language_analyzers(),
    )


def _clear_index_tables(conn: sqlite3.Connection) -> None:
    """
    Remove all indexed rows from the database tables.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection to clear in place.

    Returns
    -------
    None
        The tables are cleared in place on ``conn``.
    """
    conn.execute("DELETE FROM docstring_issues")
    conn.execute("DELETE FROM call_edges")
    conn.execute("DELETE FROM callable_refs")
    conn.execute("DELETE FROM call_records")
    conn.execute("DELETE FROM callable_ref_records")
    conn.execute("DELETE FROM embeddings")
    conn.execute("DELETE FROM symbol_index")
    conn.execute("DELETE FROM imports")
    conn.execute("DELETE FROM functions")
    conn.execute("DELETE FROM classes")
    conn.execute("DELETE FROM modules")
    conn.execute("DELETE FROM files")


def _qualified_callable_name(name: str, class_name: str | None = None) -> str:
    """
    Build the logical name used for call-graph identity.

    Parameters
    ----------
    name : str
        Unqualified function or method name.
    class_name : str | None, optional
        Owning class name for methods.

    Returns
    -------
    str
        ``Class.method`` for methods and the bare function name otherwise.
    """
    if class_name is None:
        return name
    return f"{class_name}.{name}"


def _import_alias_map(imports: list[dict[str, object]]) -> dict[str, str]:
    """
    Build a deterministic alias map for imported names.

    Parameters
    ----------
    imports : list[dict[str, object]]
        Parsed import rows from a module.

    Returns
    -------
    dict[str, str]
        Mapping from the locally bound import name to the imported dotted
        target.
    """
    aliases: dict[str, str] = {}

    for imp in imports:
        imported = str(imp["name"])
        alias = imp["alias"]
        local_name = str(alias) if alias is not None else imported.split(".")[-1]

        if "." in imported and alias is None and "." not in local_name:
            aliases[imported] = imported

        aliases[local_name] = imported

    return aliases


def _resolve_imported_function(
    imported: str,
    module_functions: dict[str, set[str]],
) -> tuple[str, str] | None:
    """
    Resolve a directly imported same-repo function target.

    Parameters
    ----------
    imported : str
        Imported dotted target as recorded by the parser.
    module_functions : dict[str, set[str]]
        Known top-level functions keyed by module name.

    Returns
    -------
    tuple[str, str] | None
        Resolved ``(callee_module, callee_name)`` pair, or ``None`` when the
        import does not name a straightforward same-repo function.
    """
    if "." not in imported:
        return None

    module_name, function_name = imported.rsplit(".", 1)
    if function_name in module_functions.get(module_name, set()):
        return (module_name, function_name)
    return None


def _resolve_module_attribute_call(
    base: str,
    target: str,
    import_aliases: dict[str, str],
    module_functions: dict[str, set[str]],
) -> tuple[str, str] | None:
    """
    Resolve a module-qualified same-repo function call.

    Parameters
    ----------
    base : str
        Static base expression of the attribute call.
    target : str
        Attribute name being called.
    import_aliases : dict[str, str]
        Mapping of locally bound import names to imported dotted targets.
    module_functions : dict[str, set[str]]
        Known top-level functions keyed by module name.

    Returns
    -------
    tuple[str, str] | None
        Resolved ``(callee_module, callee_name)`` pair, or ``None`` when the
        call cannot be resolved conservatively.
    """
    imported = import_aliases.get(base)
    if imported is None:
        return None

    if target in module_functions.get(imported, set()):
        return (imported, target)
    return None


def _resolve_call_record(
    call: dict[str, str | int],
    *,
    caller_module: str,
    caller_class: str | None,
    import_aliases: dict[str, str],
    module_functions: dict[str, set[str]],
    class_methods: dict[tuple[str, str], set[str]],
) -> tuple[str | None, str | None, int]:
    """
    Resolve one parsed call-site record into a stored call edge.

    Parameters
    ----------
    call : dict[str, str | int]
        Parsed call-site record.
    caller_module : str
        Module containing the caller.
    caller_class : str | None
        Owning class for method callers.
    import_aliases : dict[str, str]
        Mapping of locally bound import names to imported dotted targets.
    module_functions : dict[str, set[str]]
        Known top-level functions keyed by module name.
    class_methods : dict[tuple[str, str], set[str]]
        Known method names keyed by ``(module_name, class_name)``.

    Returns
    -------
    tuple[str | None, str | None, int]
        ``(callee_module, callee_name, resolved)`` for the call edge.
    """
    kind = str(call.get("kind", "unresolved"))
    target = str(call.get("target", ""))

    candidates: set[tuple[str, str]] = set()

    if kind == "name" and target:
        imported = import_aliases.get(target)
        if imported is not None:
            resolved_import = _resolve_imported_function(imported, module_functions)
            if resolved_import is not None:
                candidates.add(resolved_import)

        if target in module_functions.get(caller_module, set()):
            candidates.add((caller_module, target))

    elif kind == "attribute" and target:
        base = str(call.get("base", ""))
        if caller_class is not None and base in {"self", "cls"}:
            methods = class_methods.get((caller_module, caller_class), set())
            if target in methods:
                candidates.add(
                    (caller_module, _qualified_callable_name(target, caller_class))
                )

        methods = class_methods.get((caller_module, base), set())
        if target in methods:
            candidates.add((caller_module, _qualified_callable_name(target, base)))

        resolved_module_call = _resolve_module_attribute_call(
            base,
            target,
            import_aliases,
            module_functions,
        )
        if resolved_module_call is not None:
            candidates.add(resolved_module_call)

    if len(candidates) == 1:
        callee_module, callee_name = next(iter(candidates))
        return (callee_module, callee_name, 1)

    return (None, None, 0)


def _embedding_text(
    *,
    module_name: str,
    symbol_name: str,
    symbol_type: str,
    signature: str | None = None,
    docstring: str | None = None,
    extra_context: tuple[str, ...] = (),
) -> str:
    """
    Build the deterministic text payload embedded for one symbol.

    Parameters
    ----------
    module_name : str
        Dotted module name that owns the symbol.
    symbol_name : str
        Logical symbol name.
    symbol_type : str
        Indexed symbol type.
    signature : str | None, optional
        Callable signature when present.
    docstring : str | None, optional
        Symbol docstring when present.
    extra_context : tuple[str, ...], optional
        Additional deterministic semantic context lines.

    Returns
    -------
    str
        Joined text payload used for embedding generation.
    """
    parts = [symbol_type, module_name, symbol_name]
    if signature:
        parts.append(signature)
    if docstring:
        parts.append(docstring)
    parts.extend(line for line in extra_context if line)
    return "\n".join(parts)


def _c_embedding_context(analysis: AnalysisResult) -> tuple[str, ...]:
    """
    Build extra semantic context lines for C-family embedding payloads.

    Parameters
    ----------
    analysis : repoindex.models.AnalysisResult
        Normalized analyzer output for one indexed source file.

    Returns
    -------
    tuple[str, ...]
        Deterministic C-specific semantic context lines.
    """
    if analysis.source_path.suffix.lower() not in {".c", ".h"}:
        return ()

    context: list[str] = []

    if analysis.module.docstring:
        context.append(f"module summary: {analysis.module.docstring}")

    local_includes = tuple(
        imp.name for imp in analysis.imports if imp.kind == "include_local"
    )
    system_includes = tuple(
        imp.name for imp in analysis.imports if imp.kind == "include_system"
    )

    if local_includes:
        context.append("local includes: " + ", ".join(local_includes))
    if system_includes:
        context.append("system includes: " + ", ".join(system_includes))

    source_path = analysis.source_path
    suffix = source_path.suffix.lower()
    paired_path: Path | None = None

    if suffix == ".c":
        candidate = source_path.with_suffix(".h")
        if candidate.exists():
            paired_path = candidate
    elif suffix == ".h":
        candidate = source_path.with_suffix(".c")
        if candidate.exists():
            paired_path = candidate

    if paired_path is not None:
        pair_label = "paired header" if suffix == ".c" else "paired source"
        try:
            pair_rel_path = paired_path.relative_to(source_path.parents[1])
        except ValueError:
            pair_rel_path = paired_path
        context.append(f"{pair_label}: {pair_rel_path.as_posix()}")

    return tuple(context)


def _python_embedding_context(
    analysis: AnalysisResult,
    function: FunctionArtifact,
    *,
    class_name: str | None = None,
) -> tuple[str, ...]:
    """
    Build extra semantic context lines for Python callable embedding payloads.

    Parameters
    ----------
    analysis : repoindex.models.AnalysisResult
        Normalized analyzer output for one indexed source file.
    function : repoindex.models.FunctionArtifact
        Function or method artifact receiving the embedding payload.
    class_name : str | None, optional
        Owning class name for method artifacts.

    Returns
    -------
    tuple[str, ...]
        Deterministic Python-specific semantic context lines.
    """
    if analysis.source_path.suffix.lower() != ".py":
        return ()

    context: list[str] = []

    if analysis.module.docstring:
        context.append(f"module summary: {analysis.module.docstring}")

    if class_name is not None:
        context.append(f"owner class: {class_name}")

    if function.has_asserts:
        context.append("assertions: present")

    decorators = function.decorators
    if decorators:
        context.append("decorators: " + ", ".join(decorators))

    if any(name in {"fixture", "pytest.fixture"} for name in decorators):
        context.append("fixture context: pytest fixture")

    if function.name in {
        "setup",
        "setUp",
        "setup_class",
        "setup_method",
        "setup_function",
        "tearDown",
        "teardown",
        "teardown_class",
        "teardown_method",
        "teardown_function",
    }:
        context.append(f"setup context: {function.name}")

    return tuple(context)


def _placeholders(values: list[int]) -> str:
    """
    Build a positional placeholder string for SQL ``IN`` clauses.

    Parameters
    ----------
    values : list[int]
        Integer values that will populate the clause.

    Returns
    -------
    str
        Comma-separated ``?`` placeholders sized to ``values``.
    """
    return ",".join("?" for _ in values)


def _delete_indexed_file_data(conn: sqlite3.Connection, file_path: str) -> None:
    """
    Remove all indexed data owned by one file.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    file_path : str
        Absolute file path whose indexed rows should be removed.

    Returns
    -------
    None
        The rows are deleted in place on ``conn``.
    """
    file_row = conn.execute(
        "SELECT id FROM files WHERE path = ?",
        (file_path,),
    ).fetchone()
    if file_row is None:
        return

    file_id = int(file_row[0])

    module_ids = [
        int(row[0])
        for row in conn.execute(
            """
            SELECT id
            FROM modules
            WHERE file_id = ?
            """,
            (file_id,),
        ).fetchall()
    ]
    symbol_ids = [
        int(row[0])
        for row in conn.execute(
            "SELECT id FROM symbol_index WHERE file_id = ?",
            (file_id,),
        ).fetchall()
    ]

    if module_ids:
        if symbol_ids:
            conn.execute(
                f"DELETE FROM embeddings WHERE object_type = 'symbol' "
                f"AND object_id IN ({_placeholders(symbol_ids)})",
                tuple(symbol_ids),
            )

        conn.execute(
            "DELETE FROM docstring_issues WHERE file_id = ?",
            (file_id,),
        )
        conn.execute(
            f"DELETE FROM imports WHERE module_id IN ({_placeholders(module_ids)})",
            tuple(module_ids),
        )
        conn.execute(
            f"DELETE FROM functions WHERE module_id IN ({_placeholders(module_ids)})",
            tuple(module_ids),
        )
        conn.execute(
            f"DELETE FROM classes WHERE module_id IN ({_placeholders(module_ids)})",
            tuple(module_ids),
        )
        conn.execute(
            f"DELETE FROM modules WHERE id IN ({_placeholders(module_ids)})",
            tuple(module_ids),
        )
    elif symbol_ids:
        conn.execute(
            f"DELETE FROM embeddings WHERE object_type = 'symbol' "
            f"AND object_id IN ({_placeholders(symbol_ids)})",
            tuple(symbol_ids),
        )
        conn.execute("DELETE FROM docstring_issues WHERE file_id = ?", (file_id,))

    conn.execute("DELETE FROM symbol_index WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM call_records WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM callable_ref_records WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM files WHERE path = ?", (file_path,))


def _current_embedding_state_matches(
    conn: sqlite3.Connection,
    backend: EmbeddingBackendSpec,
) -> bool:
    """
    Check whether stored embeddings already match the active backend state.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    backend : EmbeddingBackendSpec
        Active embedding backend metadata.

    Returns
    -------
    bool
        ``True`` when all stored embeddings use the active backend and version.
    """
    rows = conn.execute(
        "SELECT DISTINCT backend, version FROM embeddings ORDER BY backend, version"
    ).fetchall()
    if not rows:
        return True
    return rows == [(backend.name, backend.version)]


def _prune_orphaned_embeddings(conn: sqlite3.Connection) -> None:
    """
    Remove embedding rows whose indexed symbol owner no longer exists.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    None
        Orphaned embedding rows are deleted in place.
    """
    conn.execute("""
        DELETE FROM embeddings
        WHERE object_type = 'symbol'
          AND object_id NOT IN (SELECT id FROM symbol_index)
        """)


def _load_existing_file_hashes(conn: sqlite3.Connection) -> dict[str, str]:
    """
    Load indexed file hashes keyed by path.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[str, str]
        Indexed file hashes keyed by absolute path.
    """
    rows = conn.execute("SELECT path, hash FROM files ORDER BY path").fetchall()
    return {str(path): str(file_hash) for path, file_hash in rows}


def _load_existing_file_ownership(
    conn: sqlite3.Connection,
) -> dict[str, tuple[str, str]]:
    """
    Load persisted analyzer ownership keyed by path.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[str, tuple[str, str]]
        Indexed analyzer ownership keyed by absolute path.
    """
    rows = conn.execute("""
        SELECT path, analyzer_name, analyzer_version
        FROM files
        ORDER BY path
        """).fetchall()
    return {
        str(path): (str(analyzer_name), str(analyzer_version))
        for path, analyzer_name, analyzer_version in rows
    }


def _count_reused_embeddings(
    conn: sqlite3.Connection,
    reused_paths: list[str],
) -> int:
    """
    Count preserved embedding rows for unchanged files.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    reused_paths : list[str]
        Absolute file paths reused without reparsing.

    Returns
    -------
    int
        Number of embedding rows preserved for the reused files.
    """
    if not reused_paths:
        return 0

    placeholders = ",".join("?" for _ in reused_paths)
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM embeddings e
        JOIN symbol_index s
          ON e.object_type = 'symbol'
         AND e.object_id = s.id
        JOIN files f
          ON s.file_id = f.id
        WHERE f.path IN ({placeholders})
        """,
        tuple(reused_paths),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _load_module_functions(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """
    Load known top-level functions from indexed structural tables.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[str, set[str]]
        Top-level function names keyed by module name.
    """
    rows = conn.execute("""
        SELECT m.name, f.name
        FROM functions f
        JOIN modules m
          ON f.module_id = m.id
        WHERE f.class_id IS NULL
        ORDER BY m.name, f.name
        """).fetchall()
    module_functions: dict[str, set[str]] = {}
    for module_name, function_name in rows:
        module_functions.setdefault(str(module_name), set()).add(str(function_name))
    return module_functions


def _load_class_methods(conn: sqlite3.Connection) -> dict[tuple[str, str], set[str]]:
    """
    Load known methods from indexed structural tables.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[tuple[str, str], set[str]]
        Method names keyed by ``(module_name, class_name)``.
    """
    rows = conn.execute("""
        SELECT m.name, c.name, f.name
        FROM functions f
        JOIN classes c
          ON f.class_id = c.id
        JOIN modules m
          ON f.module_id = m.id
        ORDER BY m.name, c.name, f.name
        """).fetchall()
    class_methods: dict[tuple[str, str], set[str]] = {}
    for module_name, class_name, method_name in rows:
        key = (str(module_name), str(class_name))
        class_methods.setdefault(key, set()).add(str(method_name))
    return class_methods


def _load_import_aliases(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """
    Load import alias maps for indexed modules.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[str, dict[str, str]]
        Alias maps keyed by owning module name.
    """
    rows = conn.execute("""
        SELECT m.name, i.name, i.alias
        FROM imports i
        JOIN modules m
          ON i.module_id = m.id
        WHERE i.kind = 'import'
        ORDER BY m.name, i.lineno, i.name, COALESCE(i.alias, '')
        """).fetchall()
    imports_by_module: dict[str, list[dict[str, object]]] = {}
    for module_name, import_name, alias in rows:
        imports_by_module.setdefault(str(module_name), []).append(
            {
                "name": str(import_name),
                "alias": None if alias is None else str(alias),
            }
        )

    return {
        module_name: _import_alias_map(imports)
        for module_name, imports in imports_by_module.items()
    }


def _caller_class_from_owner(owner_name: str) -> str | None:
    """
    Derive the owning class name from a logical callable owner.

    Parameters
    ----------
    owner_name : str
        Logical callable owner name.

    Returns
    -------
    str | None
        Owning class name for methods, or ``None`` for top-level functions.
    """
    if "." not in owner_name:
        return None
    class_name, _method_name = owner_name.rsplit(".", 1)
    return class_name


def _rebuild_graph_indexes(conn: sqlite3.Connection) -> None:
    """
    Rebuild derived call and callable-reference edges from stored raw records.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    None
        The derived edge tables are replaced in place.
    """
    module_functions = _load_module_functions(conn)
    class_methods = _load_class_methods(conn)
    import_aliases_by_module = _load_import_aliases(conn)

    conn.execute("DELETE FROM call_edges")
    conn.execute("DELETE FROM callable_refs")

    edges: set[tuple[int, str, str, str | None, str | None, int]] = set()
    refs: set[tuple[int, str, str, str | None, str | None, int]] = set()

    call_rows = conn.execute("""
        SELECT
            file_id,
            owner_module,
            owner_name,
            kind,
            base,
            target,
            lineno,
            col_offset
        FROM call_records
        ORDER BY
            file_id,
            owner_module,
            owner_name,
            lineno,
            col_offset,
            kind,
            base,
            target
        """).fetchall()
    for (
        file_id,
        owner_module,
        owner_name,
        kind,
        base,
        target,
        _lineno,
        _col_offset,
    ) in call_rows:
        record = cast(
            "CallRecord",
            {
                "kind": str(kind),
                "base": str(base),
                "target": str(target),
            },
        )
        caller_module = str(owner_module)
        caller_name = str(owner_name)
        callee_module, callee_name, resolved = _resolve_call_record(
            record,
            caller_module=caller_module,
            caller_class=_caller_class_from_owner(caller_name),
            import_aliases=import_aliases_by_module.get(caller_module, {}),
            module_functions=module_functions,
            class_methods=class_methods,
        )
        edges.add(
            (
                int(file_id),
                caller_module,
                caller_name,
                callee_module,
                callee_name,
                resolved,
            )
        )

    ref_rows = conn.execute("""
        SELECT file_id, owner_module, owner_name, kind, base, target, lineno, col_offset
        FROM callable_ref_records
        ORDER BY
            file_id,
            owner_module,
            owner_name,
            lineno,
            col_offset,
            kind,
            base,
            target
        """).fetchall()
    for (
        file_id,
        owner_module,
        owner_name,
        kind,
        base,
        target,
        _lineno,
        _col_offset,
    ) in ref_rows:
        record = cast(
            "CallRecord",
            {
                "kind": str(kind),
                "base": str(base),
                "target": str(target),
            },
        )
        caller_module = str(owner_module)
        caller_name = str(owner_name)
        target_module, target_name, resolved = _resolve_call_record(
            record,
            caller_module=caller_module,
            caller_class=_caller_class_from_owner(caller_name),
            import_aliases=import_aliases_by_module.get(caller_module, {}),
            module_functions=module_functions,
            class_methods=class_methods,
        )
        refs.add(
            (
                int(file_id),
                caller_module,
                caller_name,
                target_module,
                target_name,
                resolved,
            )
        )

    for edge in sorted(
        edges,
        key=lambda item: (
            item[0],
            item[1],
            item[2],
            item[3] or "",
            item[4] or "",
            item[5],
        ),
    ):
        conn.execute(
            "INSERT OR IGNORE INTO call_edges"
            "(caller_file_id, caller_module, caller_name, callee_module, "
            "callee_name, resolved) VALUES (?, ?, ?, ?, ?, ?)",
            edge,
        )

    for ref_row in sorted(
        refs,
        key=lambda item: (
            item[0],
            item[1],
            item[2],
            item[3] or "",
            item[4] or "",
            item[5],
        ),
    ):
        conn.execute(
            "INSERT OR IGNORE INTO callable_refs"
            "(owner_file_id, owner_module, owner_name, target_module, "
            "target_name, resolved) VALUES (?, ?, ?, ?, ?, ?)",
            ref_row,
        )


def _record_tuple(
    file_id: int,
    owner_module: str,
    owner_name: str,
    record: CallSite,
) -> tuple[int, str, str, str, str, str, int, int]:
    """
    Normalize one raw call-style record for SQLite persistence.

    Parameters
    ----------
    file_id : int
        Integer identifier of the owner file.
    owner_module : str
        Owning module name.
    owner_name : str
        Logical owner name.
    record : repoindex.models.CallSite
        Normalized call-site record.

    Returns
    -------
    tuple[int, str, str, str, str, str, int, int]
        Normalized SQLite row values.
    """
    return (
        file_id,
        owner_module,
        owner_name,
        record.kind,
        record.base,
        record.target,
        record.lineno,
        record.col_offset,
    )


def _reference_tuple(
    file_id: int,
    owner_module: str,
    owner_name: str,
    record: CallableReference,
) -> tuple[int, str, str, str, str, str, str, int, int]:
    """
    Normalize one callable-reference record for SQLite persistence.

    Parameters
    ----------
    file_id : int
        Integer identifier of the owner file.
    owner_module : str
        Owning module name.
    owner_name : str
        Logical owner name.
    record : repoindex.models.CallableReference
        Normalized callable-reference record.

    Returns
    -------
    tuple[int, str, str, str, str, str, str, int, int]
        Normalized SQLite row values.
    """
    return (
        file_id,
        owner_module,
        owner_name,
        record.kind,
        record.ref_kind,
        record.base,
        record.target,
        record.lineno,
        record.col_offset,
    )


def _insert_symbol_index_row(
    conn: sqlite3.Connection,
    *,
    name: str,
    symbol_type: str,
    module_name: str,
    file_id: int,
    lineno: int,
) -> int:
    """
    Insert one symbol-index row and return its integer identifier.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    name : str
        Symbol name stored in the index.
    symbol_type : str
        Stable symbol kind stored in the index.
    module_name : str
        Module name owning the symbol.
    file_id : int
        Integer identifier of the owner file.
    lineno : int
        Source line of the indexed symbol.

    Returns
    -------
    int
        Inserted symbol row identifier.
    """
    cur = conn.execute(
        "INSERT INTO symbol_index"
        "(name, type, module_name, file_id, lineno) VALUES (?, ?, ?, ?, ?)",
        (name, symbol_type, module_name, file_id, lineno),
    )
    assert cur.lastrowid is not None
    return int(cur.lastrowid)


def _append_embedding_row(
    embedding_rows: list[tuple[str, int, str]],
    *,
    symbol_row_id: int,
    module_name: str,
    symbol_name: str,
    symbol_type: str,
    signature: str | None = None,
    docstring: str | None = None,
    extra_context: tuple[str, ...] = (),
) -> None:
    """
    Append one normalized symbol embedding payload to the pending batch.

    Parameters
    ----------
    embedding_rows : list[tuple[str, int, str]]
        Pending embedding rows collected for the current file.
    symbol_row_id : int
        Inserted symbol row identifier referenced by the embedding.
    module_name : str
        Module name owning the symbol.
    symbol_name : str
        Logical symbol name used for embedding text.
    symbol_type : str
        Stable symbol kind used for embedding text.
    signature : str | None, optional
        Callable or declaration signature when available.
    docstring : str | None, optional
        Symbol docstring when available.
    extra_context : tuple[str, ...], optional
        Additional analyzer-specific context lines.

    Returns
    -------
    None
        The embedding row is appended in place.
    """
    embedding_rows.append(
        (
            "symbol",
            symbol_row_id,
            _embedding_text(
                module_name=module_name,
                symbol_name=symbol_name,
                symbol_type=symbol_type,
                signature=signature,
                docstring=docstring,
                extra_context=extra_context,
            ),
        )
    )


def _persist_docstring_issues(
    conn: sqlite3.Connection,
    *,
    file_id: int,
    label: str,
    docstring: str | None,
    is_public: int,
    function_id: int | None = None,
    class_id: int | None = None,
    module_id: int | None = None,
    parameters: list[str] | None = None,
    require_callable_sections: bool = False,
    yields_value: bool = False,
    returns_value: bool = False,
    raises_exception: bool = False,
) -> None:
    """
    Persist docstring-audit findings for one indexed artifact.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    file_id : int
        Integer identifier of the owner file.
    label : str
        Stable artifact label prefixed onto each issue message.
    docstring : str | None
        Artifact docstring to validate.
    is_public : int
        Public-visibility flag passed to the validator.
    function_id : int | None, optional
        Function row identifier when the issues belong to a callable.
    class_id : int | None, optional
        Class row identifier when the issues belong to a class.
    module_id : int | None, optional
        Module row identifier when the issues belong to a module.
    parameters : list[str] | None, optional
        Callable parameters used by the validator.
    require_callable_sections : bool, optional
        Whether callable-specific sections must be present.
    yields_value : bool, optional
        Whether the callable yields values.
    returns_value : bool, optional
        Whether the callable returns values.
    raises_exception : bool, optional
        Whether the callable raises exceptions.

    Returns
    -------
    None
        Matching docstring issues are inserted in place.
    """
    for issue_type, message in validate_docstring(
        docstring,
        is_public=is_public,
        parameters=parameters or [],
        require_callable_sections=require_callable_sections,
        yields_value=yields_value,
        returns_value=returns_value,
        raises_exception=raises_exception,
    ):
        conn.execute(
            "INSERT INTO docstring_issues"
            "(file_id, function_id, class_id, module_id, issue_type, message) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                file_id,
                function_id,
                class_id,
                module_id,
                issue_type,
                f"{label}: {message}",
            ),
        )


def _persist_module_artifacts(
    conn: sqlite3.Connection,
    *,
    file_id: int,
    analysis: AnalysisResult,
    embedding_rows: list[tuple[str, int, str]],
) -> tuple[str, int, tuple[str, ...]]:
    """
    Persist module-level rows for one analyzed file.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    file_id : int
        Integer identifier of the owner file.
    analysis : repoindex.models.AnalysisResult
        Normalized analyzer output for the file.
    embedding_rows : list[tuple[str, int, str]]
        Pending embedding rows collected for the file.

    Returns
    -------
    tuple[str, int, tuple[str, ...]]
        Module name, inserted module row identifier, and C-family embedding
        context for downstream artifacts.
    """
    module = analysis.module
    module_name = module.name
    c_embedding_context = _c_embedding_context(analysis)
    cur = conn.execute(
        "INSERT INTO modules"
        "(file_id, name, docstring, has_docstring) VALUES (?, ?, ?, ?)",
        (
            file_id,
            module_name,
            module.docstring,
            module.has_docstring,
        ),
    )
    assert cur.lastrowid is not None
    module_id = int(cur.lastrowid)
    symbol_row_id = _insert_symbol_index_row(
        conn,
        name=module_name,
        symbol_type="module",
        module_name=module_name,
        file_id=file_id,
        lineno=1,
    )
    _append_embedding_row(
        embedding_rows,
        symbol_row_id=symbol_row_id,
        module_name=module_name,
        symbol_name=module_name,
        symbol_type="module",
        docstring=module.docstring,
        extra_context=c_embedding_context,
    )
    _persist_docstring_issues(
        conn,
        file_id=file_id,
        module_id=module_id,
        label=f"Module {module_name}",
        docstring=module.docstring,
        is_public=1,
    )
    return module_name, module_id, c_embedding_context


def _persist_class_artifacts(
    conn: sqlite3.Connection,
    *,
    file_id: int,
    module_id: int,
    module_name: str,
    analysis: AnalysisResult,
    c_embedding_context: tuple[str, ...],
    embedding_rows: list[tuple[str, int, str]],
    call_rows: list[tuple[int, str, str, str, str, str, int, int]],
    ref_rows: list[tuple[int, str, str, str, str, str, str, int, int]],
) -> None:
    """
    Persist classes and methods for one analyzed file.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    file_id : int
        Integer identifier of the owner file.
    module_id : int
        Inserted module row identifier.
    module_name : str
        Module name owning the classes.
    analysis : repoindex.models.AnalysisResult
        Normalized analyzer output for the file.
    c_embedding_context : tuple[str, ...]
        C-family embedding context reused by declarations and classes.
    embedding_rows : list[tuple[str, int, str]]
        Pending embedding rows collected for the file.
    call_rows : list[tuple[int, str, str, str, str, str, int, int]]
        Pending call rows collected for the file.
    ref_rows : list[tuple[int, str, str, str, str, str, str, int, int]]
        Pending callable-reference rows collected for the file.

    Returns
    -------
    None
        Class and method rows are inserted in place.
    """
    for cls in analysis.classes:
        cur = conn.execute(
            "INSERT INTO classes"
            "(module_id, name, lineno, end_lineno, docstring, has_docstring) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                module_id,
                cls.name,
                cls.lineno,
                cls.end_lineno,
                cls.docstring,
                cls.has_docstring,
            ),
        )
        assert cur.lastrowid is not None
        class_id = int(cur.lastrowid)
        symbol_row_id = _insert_symbol_index_row(
            conn,
            name=cls.name,
            symbol_type="class",
            module_name=module_name,
            file_id=file_id,
            lineno=cls.lineno,
        )
        _append_embedding_row(
            embedding_rows,
            symbol_row_id=symbol_row_id,
            module_name=module_name,
            symbol_name=cls.name,
            symbol_type="class",
            docstring=cls.docstring,
            extra_context=c_embedding_context,
        )
        _persist_docstring_issues(
            conn,
            file_id=file_id,
            class_id=class_id,
            label=f"Class {cls.name}",
            docstring=cls.docstring,
            is_public=1,
        )

        for method in cls.methods:
            logical_name = _qualified_callable_name(method.name, cls.name)
            python_embedding_context = _python_embedding_context(
                analysis,
                method,
                class_name=cls.name,
            )
            cur = conn.execute(
                "INSERT INTO functions"
                "(module_id, class_id, name, lineno, end_lineno, signature, "
                "docstring, has_docstring, is_method, is_public) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    module_id,
                    class_id,
                    method.name,
                    method.lineno,
                    method.end_lineno,
                    method.signature,
                    method.docstring,
                    method.has_docstring,
                    method.is_method,
                    method.is_public,
                ),
            )
            assert cur.lastrowid is not None
            function_id = int(cur.lastrowid)
            symbol_row_id = _insert_symbol_index_row(
                conn,
                name=method.name,
                symbol_type="method",
                module_name=module_name,
                file_id=file_id,
                lineno=method.lineno,
            )
            _append_embedding_row(
                embedding_rows,
                symbol_row_id=symbol_row_id,
                module_name=module_name,
                symbol_name=logical_name,
                symbol_type="method",
                signature=method.signature,
                docstring=method.docstring,
                extra_context=python_embedding_context or c_embedding_context,
            )
            _persist_docstring_issues(
                conn,
                file_id=file_id,
                function_id=function_id,
                label=f"Method {cls.name}.{method.name}",
                docstring=method.docstring,
                is_public=method.is_public,
                parameters=list(method.parameters),
                require_callable_sections=True,
                yields_value=bool(method.yields_value),
                returns_value=bool(method.returns_value),
                raises_exception=bool(method.raises),
            )
            for call in method.calls:
                call_rows.append(
                    _record_tuple(file_id, module_name, logical_name, call)
                )
            for ref in method.callable_refs:
                ref_rows.append(
                    _reference_tuple(file_id, module_name, logical_name, ref)
                )


def _persist_function_artifacts(
    conn: sqlite3.Connection,
    *,
    file_id: int,
    module_id: int,
    module_name: str,
    analysis: AnalysisResult,
    c_embedding_context: tuple[str, ...],
    embedding_rows: list[tuple[str, int, str]],
    call_rows: list[tuple[int, str, str, str, str, str, int, int]],
    ref_rows: list[tuple[int, str, str, str, str, str, str, int, int]],
) -> None:
    """
    Persist top-level functions for one analyzed file.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    file_id : int
        Integer identifier of the owner file.
    module_id : int
        Inserted module row identifier.
    module_name : str
        Module name owning the functions.
    analysis : repoindex.models.AnalysisResult
        Normalized analyzer output for the file.
    c_embedding_context : tuple[str, ...]
        C-family embedding context reused by declarations and functions.
    embedding_rows : list[tuple[str, int, str]]
        Pending embedding rows collected for the file.
    call_rows : list[tuple[int, str, str, str, str, str, int, int]]
        Pending call rows collected for the file.
    ref_rows : list[tuple[int, str, str, str, str, str, str, int, int]]
        Pending callable-reference rows collected for the file.

    Returns
    -------
    None
        Function rows are inserted in place.
    """
    for fn in analysis.functions:
        python_embedding_context = _python_embedding_context(analysis, fn)
        cur = conn.execute(
            "INSERT INTO functions"
            "(module_id, class_id, name, lineno, end_lineno, signature, "
            "docstring, has_docstring, is_method, is_public) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                module_id,
                None,
                fn.name,
                fn.lineno,
                fn.end_lineno,
                fn.signature,
                fn.docstring,
                fn.has_docstring,
                fn.is_method,
                fn.is_public,
            ),
        )
        assert cur.lastrowid is not None
        function_id = int(cur.lastrowid)
        symbol_row_id = _insert_symbol_index_row(
            conn,
            name=fn.name,
            symbol_type="function",
            module_name=module_name,
            file_id=file_id,
            lineno=fn.lineno,
        )
        _append_embedding_row(
            embedding_rows,
            symbol_row_id=symbol_row_id,
            module_name=module_name,
            symbol_name=fn.name,
            symbol_type="function",
            signature=fn.signature,
            docstring=fn.docstring,
            extra_context=python_embedding_context or c_embedding_context,
        )
        _persist_docstring_issues(
            conn,
            file_id=file_id,
            function_id=function_id,
            label=f"Function {fn.name}",
            docstring=fn.docstring,
            is_public=fn.is_public,
            parameters=list(fn.parameters),
            require_callable_sections=True,
            yields_value=bool(fn.yields_value),
            returns_value=bool(fn.returns_value),
            raises_exception=bool(fn.raises),
        )
        for call in fn.calls:
            call_rows.append(_record_tuple(file_id, module_name, fn.name, call))
        for ref in fn.callable_refs:
            ref_rows.append(_reference_tuple(file_id, module_name, fn.name, ref))


def _persist_declaration_artifacts(
    conn: sqlite3.Connection,
    *,
    file_id: int,
    module_name: str,
    analysis: AnalysisResult,
    c_embedding_context: tuple[str, ...],
    embedding_rows: list[tuple[str, int, str]],
) -> None:
    """
    Persist declaration-style symbol artifacts for one analyzed file.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    file_id : int
        Integer identifier of the owner file.
    module_name : str
        Module name owning the declarations.
    analysis : repoindex.models.AnalysisResult
        Normalized analyzer output for the file.
    c_embedding_context : tuple[str, ...]
        C-family embedding context reused by declaration embeddings.
    embedding_rows : list[tuple[str, int, str]]
        Pending embedding rows collected for the file.

    Returns
    -------
    None
        Declaration symbol rows are inserted in place.
    """
    for decl in analysis.declarations:
        symbol_row_id = _insert_symbol_index_row(
            conn,
            name=decl.name,
            symbol_type=decl.kind,
            module_name=module_name,
            file_id=file_id,
            lineno=decl.lineno,
        )
        _append_embedding_row(
            embedding_rows,
            symbol_row_id=symbol_row_id,
            module_name=module_name,
            symbol_name=decl.name,
            symbol_type=decl.kind,
            signature=decl.signature,
            docstring=decl.docstring,
            extra_context=c_embedding_context,
        )


def _persist_import_artifacts(
    conn: sqlite3.Connection,
    *,
    module_id: int,
    analysis: AnalysisResult,
) -> None:
    """
    Persist import rows for one analyzed file.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    module_id : int
        Inserted module row identifier.
    analysis : repoindex.models.AnalysisResult
        Normalized analyzer output for the file.

    Returns
    -------
    None
        Import rows are inserted in place.
    """
    for imp in analysis.imports:
        conn.execute(
            "INSERT INTO imports(module_id, name, alias, kind, lineno) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                module_id,
                imp.name,
                imp.alias,
                imp.kind,
                imp.lineno,
            ),
        )


def _flush_persisted_relationship_rows(
    conn: sqlite3.Connection,
    *,
    call_rows: list[tuple[int, str, str, str, str, str, int, int]],
    ref_rows: list[tuple[int, str, str, str, str, str, str, int, int]],
) -> None:
    """
    Flush pending call and callable-reference rows to SQLite.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    call_rows : list[tuple[int, str, str, str, str, str, int, int]]
        Pending normalized call rows.
    ref_rows : list[tuple[int, str, str, str, str, str, str, int, int]]
        Pending normalized callable-reference rows.

    Returns
    -------
    None
        Relationship rows are inserted in deterministic order.
    """
    for row in sorted(call_rows):
        conn.execute(
            "INSERT INTO call_records"
            "(file_id, owner_module, owner_name, kind, base, target, "
            "lineno, col_offset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )

    for ref_row in sorted(ref_rows):
        conn.execute(
            "INSERT INTO callable_ref_records"
            "(file_id, owner_module, owner_name, kind, ref_kind, base, "
            "target, lineno, col_offset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ref_row,
        )


def _flush_embedding_rows(
    conn: sqlite3.Connection,
    *,
    embedding_rows: list[tuple[str, int, str]],
    backend: EmbeddingBackendSpec,
) -> int:
    """
    Persist pending embedding payloads for one analyzed file.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    embedding_rows : list[tuple[str, int, str]]
        Pending embedding payloads keyed by object type and identifier.
    backend : EmbeddingBackendSpec
        Active embedding backend metadata.

    Returns
    -------
    int
        Number of embedding rows written.
    """
    for object_type, object_id, text in sorted(
        embedding_rows,
        key=lambda item: item[:2],
    ):
        conn.execute(
            "INSERT INTO embeddings"
            "(object_type, object_id, backend, version, dim, vector) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                object_type,
                object_id,
                backend.name,
                backend.version,
                backend.dim,
                serialize_vector(embed_text(text)),
            ),
        )

    return len(embedding_rows)


def _store_analysis(
    conn: sqlite3.Connection,
    file_metadata: FileMetadataSnapshot,
    analysis: AnalysisResult,
    *,
    backend: EmbeddingBackendSpec,
) -> int:
    """
    Persist one parsed file snapshot into the index.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    file_metadata : repoindex.models.FileMetadataSnapshot
        Stable file metadata for the analyzed file.
    analysis : repoindex.models.AnalysisResult
        Normalized analyzer output for the file.
    backend : EmbeddingBackendSpec
        Active embedding backend metadata.

    Returns
    -------
    int
        Number of embeddings recomputed for the file.
    """
    embedding_rows: list[tuple[str, int, str]] = []
    call_rows: list[tuple[int, str, str, str, str, str, int, int]] = []
    ref_rows: list[tuple[int, str, str, str, str, str, str, int, int]] = []

    cur = conn.execute(
        "INSERT INTO files"
        "(path, hash, mtime, size, analyzer_name, analyzer_version) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(file_metadata.path),
            file_metadata.sha256,
            file_metadata.mtime,
            file_metadata.size,
            file_metadata.analyzer_name,
            file_metadata.analyzer_version,
        ),
    )
    assert cur.lastrowid is not None
    file_id = int(cur.lastrowid)
    module_name, module_id, c_embedding_context = _persist_module_artifacts(
        conn,
        file_id=file_id,
        analysis=analysis,
        embedding_rows=embedding_rows,
    )
    _persist_class_artifacts(
        conn,
        file_id=file_id,
        module_id=module_id,
        module_name=module_name,
        analysis=analysis,
        c_embedding_context=c_embedding_context,
        embedding_rows=embedding_rows,
        call_rows=call_rows,
        ref_rows=ref_rows,
    )
    _persist_function_artifacts(
        conn,
        file_id=file_id,
        module_id=module_id,
        module_name=module_name,
        analysis=analysis,
        c_embedding_context=c_embedding_context,
        embedding_rows=embedding_rows,
        call_rows=call_rows,
        ref_rows=ref_rows,
    )
    _persist_declaration_artifacts(
        conn,
        file_id=file_id,
        module_name=module_name,
        analysis=analysis,
        c_embedding_context=c_embedding_context,
        embedding_rows=embedding_rows,
    )
    _persist_import_artifacts(
        conn,
        module_id=module_id,
        analysis=analysis,
    )
    _flush_persisted_relationship_rows(
        conn,
        call_rows=call_rows,
        ref_rows=ref_rows,
    )
    return _flush_embedding_rows(
        conn,
        embedding_rows=embedding_rows,
        backend=backend,
    )


def _snapshot_from_metadata(meta: dict[str, object]) -> FileMetadataSnapshot:
    """
    Convert scanner metadata into the normalized file snapshot model.

    Parameters
    ----------
    meta : dict[str, object]
        Scanner metadata mapping.

    Returns
    -------
    repoindex.models.FileMetadataSnapshot
        Normalized file metadata snapshot.
    """
    mtime = cast("float | int", meta["mtime"])
    size = cast("int | str", meta["size"])
    return FileMetadataSnapshot(
        path=Path(str(meta["path"])),
        sha256=str(meta["hash"]),
        mtime=float(mtime),
        size=int(size),
    )


def _snapshot_with_analyzer(
    snapshot: FileMetadataSnapshot,
    analyzer: LanguageAnalyzer,
) -> FileMetadataSnapshot:
    """
    Attach analyzer ownership metadata to a file snapshot.

    Parameters
    ----------
    snapshot : repoindex.models.FileMetadataSnapshot
        Base file metadata snapshot.
    analyzer : repoindex.contracts.LanguageAnalyzer
        Analyzer responsible for the file.

    Returns
    -------
    repoindex.models.FileMetadataSnapshot
        Snapshot carrying analyzer ownership information.
    """
    return FileMetadataSnapshot(
        path=snapshot.path,
        sha256=snapshot.sha256,
        mtime=snapshot.mtime,
        size=snapshot.size,
        analyzer_name=str(analyzer.name),
        analyzer_version=str(analyzer.version),
    )


def _persist_runtime_inventory(
    conn: sqlite3.Connection,
    *,
    backend_name: str,
    backend_version: str,
    coverage_complete: bool,
    analyzers: list[LanguageAnalyzer],
) -> None:
    """
    Persist backend and analyzer inventory for one successful index run.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    backend_name : str
        Active backend name.
    backend_version : str
        Active backend version.
    coverage_complete : bool
        Whether canonical-directory coverage had no gaps.
    analyzers : list[repoindex.contracts.LanguageAnalyzer]
        Active analyzers for the run.

    Returns
    -------
    None
        Inventory rows are replaced in place on ``conn``.
    """
    conn.execute("DELETE FROM index_runtime")
    conn.execute("DELETE FROM index_analyzers")
    conn.execute(
        """
        INSERT INTO index_runtime(
            singleton,
            backend_name,
            backend_version,
            coverage_complete
        ) VALUES (?, ?, ?, ?)
        """,
        (1, backend_name, backend_version, int(coverage_complete)),
    )

    for analyzer in sorted(analyzers, key=lambda item: str(item.name)):
        conn.execute(
            """
            INSERT INTO index_analyzers(name, version, discovery_globs)
            VALUES (?, ?, ?)
            """,
            (
                str(analyzer.name),
                str(analyzer.version),
                json.dumps(tuple(analyzer.discovery_globs)),
            ),
        )


def _dot_similarity(left: list[float], right: list[float]) -> float:
    """
    Compute a dot-product similarity between normalized vectors.

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


class SQLiteIndexBackend:
    """
    Concrete SQLite backend used by the current repository index.

    This backend keeps the existing SQLite schema and query semantics stable
    while concentrating indexing-side persistence behind one object.
    """

    name = "sqlite"
    version = SCHEMA_VERSION

    def load_runtime_inventory(
        self,
        root: Path,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> tuple[str, str, int] | None:
        """
        Return persisted backend and coverage metadata for the last index run.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        tuple[str, str, int] | None
            Stored ``(backend_name, backend_version, coverage_complete)``
            tuple, or ``None`` when no runtime inventory has been recorded.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            row = conn.execute("""
                SELECT backend_name, backend_version, coverage_complete
                FROM index_runtime
                WHERE singleton = 1
                """).fetchone()
            if row is None:
                return None
            return (str(row[0]), str(row[1]), int(row[2]))
        finally:
            if owns_connection:
                conn.close()

    def load_analyzer_inventory(
        self,
        root: Path,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> list[tuple[str, str, str]]:
        """
        Return persisted analyzer inventory for the last index run.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[tuple[str, str, str]]
            Stored analyzer rows as ``(name, version, discovery_globs_json)``
            ordered by analyzer name.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            rows = conn.execute("""
                SELECT name, version, discovery_globs
                FROM index_analyzers
                ORDER BY name
                """).fetchall()
            return [
                (str(name), str(version), str(globs)) for name, version, globs in rows
            ]
        finally:
            if owns_connection:
                conn.close()

    def initialize(self, root: Path) -> None:
        """
        Prepare the repository-local SQLite database.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose backend state should exist.

        Returns
        -------
        None
            The SQLite schema is created or refreshed in place.
        """
        init_db(root)

    def open_connection(self, root: Path) -> sqlite3.Connection:
        """
        Open a SQLite connection for one repository index.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index database should be opened.

        Returns
        -------
        sqlite3.Connection
            Open SQLite connection.
        """
        self.initialize(root)
        return sqlite3.connect(get_db_path(root))

    def list_symbols_in_module(
        self,
        root: Path,
        module: str,
        *,
        prefix: str | None = None,
        limit: int = 20,
        conn: sqlite3.Connection | None = None,
    ) -> list[SymbolRow]:
        """
        Return indexed symbols belonging to one module.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        module : str
            Dotted module name to expand.
        prefix : str | None, optional
            Repo-root-relative path prefix used to restrict symbol files.
        limit : int, optional
            Maximum number of symbol rows to return.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[repoindex.types.SymbolRow]
            Indexed symbols belonging to the requested module.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            normalized_prefix = normalize_prefix(root, prefix)
            prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
            rows = conn.execute(
                f"""
                SELECT s.type, s.module_name, s.name, f.path, s.lineno
                FROM symbol_index s
                JOIN files f
                  ON s.file_id = f.id
                WHERE s.module_name = ?
                {prefix_sql}
                LIMIT ?
                """,
                (module, *prefix_params, limit),
            ).fetchall()
            return [
                (str(t), str(m), str(n), str(f), int(lineno))
                for t, m, n, f, lineno in rows
            ]
        finally:
            if owns_connection:
                conn.close()

    def find_symbol(
        self,
        root: Path,
        name: str,
        *,
        prefix: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[SymbolRow]:
        """
        Find exact symbol-name matches in the index.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        name : str
            Exact symbol name to search for.
        prefix : str | None, optional
            Repo-root-relative path prefix used to restrict symbol files.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[repoindex.types.SymbolRow]
            Matching symbol rows ordered deterministically.
        """
        owns_connection = conn is None
        normalized_prefix = normalize_prefix(root, prefix)
        if conn is None:
            conn = self.open_connection(root)
        try:
            prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
            rows = conn.execute(
                f"""
                SELECT s.type, s.module_name, s.name, f.path, s.lineno
                FROM symbol_index s
                JOIN files f
                  ON s.file_id = f.id
                WHERE s.name = ?
                {prefix_sql}
                ORDER BY s.type, s.module_name, f.path, s.lineno
                """,
                (name, *prefix_params),
            ).fetchall()
            return [
                (str(t), str(m), str(n), str(f), int(lineno))
                for t, m, n, f, lineno in rows
            ]
        finally:
            if owns_connection:
                conn.close()

    def docstring_issues(
        self,
        root: Path,
        *,
        prefix: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[tuple[str, str]]:
        """
        Return indexed docstring validation issues.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        prefix : str | None, optional
            Repo-root-relative path prefix used to restrict issue ownership.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[tuple[str, str]]
            Issue rows as ``(issue_type, message)`` tuples.
        """
        owns_connection = conn is None
        normalized_prefix = normalize_prefix(root, prefix)
        if conn is None:
            conn = self.open_connection(root)
        try:
            prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
            rows = conn.execute(
                f"""
                SELECT di.issue_type, di.message
                FROM docstring_issues di
                JOIN files f
                  ON di.file_id = f.id
                WHERE 1 = 1
                {prefix_sql}
                ORDER BY di.issue_type, di.message
                """,
                tuple(prefix_params),
            ).fetchall()
            return [(str(t), str(m)) for t, m in rows]
        finally:
            if owns_connection:
                conn.close()

    def find_call_edges(
        self,
        root: Path,
        name: str,
        *,
        module: str | None = None,
        incoming: bool = False,
        prefix: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[CallEdgeRow]:
        """
        Find exact call edges for a caller or callee logical name.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        name : str
            Exact logical caller or callee name to search for.
        module : str | None, optional
            Optional module qualifier used to restrict the result set.
        incoming : bool, optional
            Whether to return incoming edges for the callee.
        prefix : str | None, optional
            Repo-root-relative path prefix used to restrict caller files.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[tuple[str, str, str | None, str | None, int]]
            Matching call-edge rows ordered deterministically.
        """
        owns_connection = conn is None
        normalized_prefix = normalize_prefix(root, prefix)
        if conn is None:
            conn = self.open_connection(root)

        direction_column = "callee_name" if incoming else "caller_name"
        module_column = "callee_module" if incoming else "caller_module"
        prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")

        query = f"""
            SELECT
                ce.caller_module,
                ce.caller_name,
                ce.callee_module,
                ce.callee_name,
                ce.resolved
            FROM call_edges ce
            JOIN files f
              ON ce.caller_file_id = f.id
            WHERE {direction_column} = ?
            {prefix_sql}
        """
        params: list[str] = [name, *prefix_params]

        if module is not None:
            query += f" AND {module_column} = ?"
            params.append(module)

        query += """
            ORDER BY
                caller_module,
                caller_name,
                COALESCE(callee_module, ''),
                COALESCE(callee_name, ''),
                resolved
        """

        try:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                (
                    str(caller_module),
                    str(caller_name),
                    None if callee_module is None else str(callee_module),
                    None if callee_name is None else str(callee_name),
                    int(resolved),
                )
                for (
                    caller_module,
                    caller_name,
                    callee_module,
                    callee_name,
                    resolved,
                ) in rows
            ]
        finally:
            if owns_connection:
                conn.close()

    def find_callable_refs(
        self,
        root: Path,
        name: str,
        *,
        module: str | None = None,
        incoming: bool = False,
        prefix: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[CallableRefRow]:
        """
        Find exact callable-object references for an owner or target.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        name : str
            Exact logical owner or referenced target name to search for.
        module : str | None, optional
            Optional module qualifier used to restrict the result set.
        incoming : bool, optional
            Whether to return incoming references for the target.
        prefix : str | None, optional
            Repo-root-relative path prefix used to restrict owner files.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[tuple[str, str, str | None, str | None, int]]
            Matching callable-reference rows ordered deterministically.
        """
        owns_connection = conn is None
        normalized_prefix = normalize_prefix(root, prefix)
        if conn is None:
            conn = self.open_connection(root)

        direction_column = "target_name" if incoming else "owner_name"
        module_column = "target_module" if incoming else "owner_module"
        prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")

        query = f"""
            SELECT
                cr.owner_module,
                cr.owner_name,
                cr.target_module,
                cr.target_name,
                cr.resolved
            FROM callable_refs cr
            JOIN files f
              ON cr.owner_file_id = f.id
            WHERE {direction_column} = ?
            {prefix_sql}
        """
        params: list[str] = [name, *prefix_params]

        if module is not None:
            query += f" AND {module_column} = ?"
            params.append(module)

        query += """
            ORDER BY
                owner_module,
                owner_name,
                COALESCE(target_module, ''),
                COALESCE(target_name, ''),
                resolved
        """

        try:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                (
                    str(owner_module),
                    str(owner_name),
                    None if target_module is None else str(target_module),
                    None if target_name is None else str(target_name),
                    int(resolved),
                )
                for (
                    owner_module,
                    owner_name,
                    target_module,
                    target_name,
                    resolved,
                ) in rows
            ]
        finally:
            if owns_connection:
                conn.close()

    def find_include_edges(
        self,
        root: Path,
        name: str,
        *,
        module: str | None = None,
        incoming: bool = False,
        prefix: str | None = None,
        conn: sqlite3.Connection | None = None,
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
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[repoindex.types.IncludeEdgeRow]
            Matching include-edge rows ordered deterministically as
            ``(owner_module, target_name, kind, lineno)`` tuples.
        """
        owns_connection = conn is None
        normalized_prefix = normalize_prefix(root, prefix)
        if conn is None:
            conn = self.open_connection(root)

        prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
        query = f"""
            SELECT
                m.name,
                i.name,
                i.kind,
                i.lineno
            FROM imports i
            JOIN modules m
              ON i.module_id = m.id
            JOIN files f
              ON m.file_id = f.id
            WHERE i.kind IN ('include_local', 'include_system')
            {prefix_sql}
        """
        params: list[str] = [*prefix_params]

        if incoming:
            query += " AND i.name = ?"
            params.append(name)
            if module is not None:
                query += " AND m.name = ?"
                params.append(module)
        else:
            query += " AND m.name = ?"
            params.append(name)

        query += """
            ORDER BY
                m.name,
                i.lineno,
                i.name,
                i.kind
        """

        try:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                (str(owner_module), str(target_name), str(kind), int(lineno))
                for owner_module, target_name, kind, lineno in rows
            ]
        finally:
            if owns_connection:
                conn.close()

    def find_logical_symbols(
        self,
        root: Path,
        module_name: str,
        logical_name: str,
        *,
        prefix: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> list[SymbolRow]:
        """
        Resolve a logical callable name back to indexed symbol rows.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        module_name : str
            Dotted module that owns the logical symbol.
        logical_name : str
            Logical symbol identity such as ``helper`` or ``Class.method``.
        prefix : str | None, optional
            Repo-root-relative path prefix used to restrict symbol files.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[repoindex.types.SymbolRow]
            Matching indexed symbol rows ordered deterministically.
        """
        owns_connection = conn is None
        normalized_prefix = normalize_prefix(root, prefix)
        if conn is None:
            conn = self.open_connection(root)

        try:
            if "." in logical_name:
                class_name, method_name = logical_name.rsplit(".", 1)
                prefix_sql, prefix_params = prefix_clause(normalized_prefix, "fp.path")
                rows = conn.execute(
                    f"""
                    SELECT
                        s.type,
                        s.module_name,
                        s.name,
                        fp.path,
                        s.lineno
                    FROM functions fn
                    JOIN classes c
                      ON fn.class_id = c.id
                    JOIN modules m
                      ON fn.module_id = m.id
                    JOIN symbol_index s
                      ON s.type = 'method'
                     AND s.module_name = m.name
                     AND s.name = fn.name
                     AND s.lineno = fn.lineno
                    JOIN files fp
                      ON s.file_id = fp.id
                    WHERE m.name = ? AND c.name = ? AND fn.name = ?
                    {prefix_sql}
                    ORDER BY fp.path, s.lineno, s.name
                    """,
                    (module_name, class_name, method_name, *prefix_params),
                ).fetchall()
            else:
                prefix_sql, prefix_params = prefix_clause(normalized_prefix, "f.path")
                rows = conn.execute(
                    f"""
                    SELECT s.type, s.module_name, s.name, f.path, s.lineno
                    FROM symbol_index s
                    JOIN files f
                      ON s.file_id = f.id
                    WHERE s.module_name = ?
                      AND (s.name = ? OR (s.type = 'module' AND s.module_name = ?))
                    {prefix_sql}
                    ORDER BY s.type, s.module_name, f.path, s.lineno
                    """,
                    (module_name, logical_name, logical_name, *prefix_params),
                ).fetchall()

            return [
                (str(t), str(m), str(n), str(f), int(lineno))
                for t, m, n, f, lineno in rows
            ]
        finally:
            if owns_connection:
                conn.close()

    def logical_symbol_name(
        self,
        root: Path,
        symbol: SymbolRow,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> str:
        """
        Return the logical graph identity for one indexed symbol row.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        symbol : repoindex.types.SymbolRow
            Indexed symbol row whose logical identity should be resolved.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        str
            Logical symbol identity used by call edges and callable references.
        """
        symbol_type, module_name, name, _file_path, lineno = symbol
        if symbol_type != "method":
            return module_name if symbol_type == "module" else name

        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)

        try:
            row = conn.execute(
                """
                SELECT c.name
                FROM functions f
                JOIN classes c
                  ON f.class_id = c.id
                JOIN modules m
                  ON f.module_id = m.id
                WHERE m.name = ? AND f.name = ? AND f.lineno = ?
                ORDER BY c.name
                LIMIT 1
                """,
                (module_name, name, lineno),
            ).fetchone()
            if row is None:
                return name
            return f"{str(row[0])}.{name}"
        finally:
            if owns_connection:
                conn.close()

    def embedding_inventory(
        self,
        root: Path,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> list[EmbeddingInventoryRow]:
        """
        Return stored embedding inventory grouped by backend metadata.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        list[tuple[str, str, int, int]]
            Rows as ``(backend, version, dim, count)`` ordered deterministically.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            rows = conn.execute("""
                SELECT backend, version, dim, COUNT(*)
                FROM embeddings
                GROUP BY backend, version, dim
                ORDER BY backend, version, dim
                """).fetchall()
            return [
                (str(backend), str(version), int(dim), int(count))
                for backend, version, dim, count in rows
            ]
        finally:
            if owns_connection:
                conn.close()

    def embedding_candidates(
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
        Return ranked symbol candidates using stored embedding similarity.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        query : str
            User query string.
        limit : int
            Maximum number of ranked results to return.
        min_score : float
            Minimum similarity threshold for emitted results.
        prefix : str | None, optional
            Repo-root-relative path prefix used to restrict matched symbol files.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        repoindex.types.ChannelResults
            Ranked symbol candidates ordered by descending similarity and stable
            symbol identity.
        """
        owns_connection = conn is None
        normalized_prefix = normalize_prefix(root, prefix)
        if conn is None:
            conn = self.open_connection(root)

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

                score = _dot_similarity(query_vector, deserialize_vector(blob, dim=dim))
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

    def prune_orphaned_embeddings(
        self,
        root: Path,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """
        Remove embedding rows whose owning symbol no longer exists.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be cleaned.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        None
            Orphaned embedding rows are removed in place.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            _prune_orphaned_embeddings(conn)
            if owns_connection:
                conn.commit()
        finally:
            if owns_connection:
                conn.close()

    def load_existing_file_hashes(
        self,
        root: Path,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, str]:
        """
        Load indexed file hashes used for incremental reuse decisions.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        dict[str, str]
            Indexed file hashes keyed by absolute file path.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            return _load_existing_file_hashes(conn)
        finally:
            if owns_connection:
                conn.close()

    def load_existing_file_ownership(
        self,
        root: Path,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, tuple[str, str]]:
        """
        Load analyzer ownership for indexed files.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        dict[str, tuple[str, str]]
            Persisted analyzer ownership keyed by absolute file path.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            return _load_existing_file_ownership(conn)
        finally:
            if owns_connection:
                conn.close()

    def current_embedding_state_matches(
        self,
        root: Path,
        *,
        embedding_backend: EmbeddingBackendSpec,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """
        Check whether persisted embeddings match the active embedding backend.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        embedding_backend : EmbeddingBackendSpec
            Active embedding backend metadata.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        bool
            ``True`` when the persisted embedding metadata matches.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            return _current_embedding_state_matches(conn, embedding_backend)
        finally:
            if owns_connection:
                conn.close()

    def delete_paths(
        self,
        root: Path,
        *,
        paths: list[str],
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """
        Remove persisted rows owned by the supplied file paths.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be updated.
        paths : list[str]
            Absolute file paths to remove.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        None
            Matching persisted rows are removed in place.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            for path in sorted(paths):
                _delete_indexed_file_data(conn, path)
            if owns_connection:
                conn.commit()
        finally:
            if owns_connection:
                conn.close()

    def count_reusable_embeddings(
        self,
        root: Path,
        *,
        paths: list[str],
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """
        Count semantic artifacts reused for unchanged paths.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be queried.
        paths : list[str]
            Absolute file paths considered reusable.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        int
            Number of reusable embedding rows.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            return _count_reused_embeddings(conn, paths)
        finally:
            if owns_connection:
                conn.close()

    def persist_analysis(
        self,
        root: Path,
        *,
        file_metadata: FileMetadataSnapshot,
        analysis: AnalysisResult,
        embedding_backend: EmbeddingBackendSpec | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """
        Persist normalized artifacts for one analyzed file.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be updated.
        file_metadata : repoindex.models.FileMetadataSnapshot
            Stable file metadata snapshot.
        analysis : repoindex.models.AnalysisResult
            Normalized analyzer output.
        embedding_backend : EmbeddingBackendSpec | None, optional
            Active embedding backend metadata. When omitted, the current
            default backend is loaded.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        int
            Number of embedding rows written.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        active_backend = (
            get_embedding_backend() if embedding_backend is None else embedding_backend
        )
        try:
            written = _store_analysis(
                conn,
                file_metadata,
                analysis,
                backend=active_backend,
            )
            if owns_connection:
                conn.commit()
            return written
        finally:
            if owns_connection:
                conn.close()

    def rebuild_derived_indexes(
        self,
        root: Path,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """
        Rebuild derived graph tables after raw persistence.

        Parameters
        ----------
        root : pathlib.Path
            Repository root whose index should be finalized.
        conn : sqlite3.Connection | None, optional
            Existing SQLite connection to reuse.

        Returns
        -------
        None
            Derived SQLite tables are refreshed in place.
        """
        owns_connection = conn is None
        if conn is None:
            conn = self.open_connection(root)
        try:
            _rebuild_graph_indexes(conn)
            if owns_connection:
                conn.commit()
        finally:
            if owns_connection:
                conn.close()


def _active_language_analyzers() -> list[LanguageAnalyzer]:
    """
    Return the language analyzers participating in the current indexing run.

    Parameters
    ----------
    None

    Returns
    -------
    list[repoindex.contracts.LanguageAnalyzer]
        Analyzer instances consulted in deterministic order.
    """
    return active_language_analyzers()


def _select_language_analyzer(
    path: Path,
    analyzers: list[LanguageAnalyzer],
) -> LanguageAnalyzer:
    """
    Select the analyzer responsible for one source path.

    Parameters
    ----------
    path : pathlib.Path
        Repository file that must be analyzed.
    analyzers : list[repoindex.contracts.LanguageAnalyzer]
        Analyzer instances consulted in deterministic order.

    Returns
    -------
    repoindex.contracts.LanguageAnalyzer
        Analyzer responsible for the file.

    Raises
    ------
    ValueError
        If no registered analyzer accepts the path.
    """
    for analyzer in analyzers:
        if analyzer.supports_path(path):
            return analyzer

    msg = f"No language analyzer registered for path: {path}"
    hint = missing_language_analyzer_hint(path)
    if hint is not None:
        msg = f"{msg}. {hint}"
    raise ValueError(msg)


def _collect_indexed_file_analyses(
    root: Path,
    indexed_paths: list[str],
    current_metadata: dict[str, dict[str, object]],
    analyzers: list[LanguageAnalyzer],
) -> tuple[list[ParsedFile], list[IndexFailure], list[IndexWarning]]:
    """
    Analyze reindexed files and collect normalized artifacts.

    Parameters
    ----------
    root : pathlib.Path
        Repository root being indexed.
    indexed_paths : list[str]
        Absolute file paths selected for reindexing.
    current_metadata : dict[str, dict[str, object]]
        Scanner metadata keyed by absolute file path.
    analyzers : list[repoindex.contracts.LanguageAnalyzer]
        Analyzer instances available for path routing.

    Returns
    -------
    tuple[list[ParsedFile], list[IndexFailure], list[IndexWarning]]
        Successful analyzed file snapshots plus deterministic failures and
        warnings.
    """
    parsed_files: list[ParsedFile] = []
    failures: list[IndexFailure] = []
    collected_warnings: list[IndexWarning] = []

    for path in indexed_paths:
        path_obj = Path(path)
        metadata_snapshot = _snapshot_from_metadata(current_metadata[path])
        analyzer = _select_language_analyzer(path_obj, analyzers)
        metadata_snapshot = _snapshot_with_analyzer(metadata_snapshot, analyzer)
        try:
            with warnings.catch_warnings(record=True) as warning_records:
                warnings.simplefilter("always")
                analysis = analyzer.analyze_file(path_obj, root)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            failures.append(
                IndexFailure(
                    path=path,
                    analyzer_name=str(analyzer.name),
                    error_type=type(exc).__name__,
                    reason=str(exc),
                )
            )
            continue
        for warning_record in warning_records:
            collected_warnings.append(
                IndexWarning(
                    path=path,
                    analyzer_name=str(analyzer.name),
                    warning_type=warning_record.category.__name__,
                    line=warning_record.lineno,
                    reason=str(warning_record.message),
                )
            )
        parsed_files.append((path_obj, metadata_snapshot, analysis))

    return parsed_files, failures, collected_warnings


def _persist_indexed_file_analyses(
    root: Path,
    *,
    conn: sqlite3.Connection,
    sqlite_backend: SQLiteIndexBackend,
    parsed_files: list[ParsedFile],
    embedding_backend: EmbeddingBackendSpec,
) -> int:
    """
    Persist analyzed file snapshots through the selected index backend.

    Parameters
    ----------
    root : pathlib.Path
        Repository root being indexed.
    conn : sqlite3.Connection
        Open backend connection reused across writes.
    sqlite_backend : repoindex.indexer.SQLiteIndexBackend
        Concrete backend receiving normalized artifacts.
    parsed_files : list[ParsedFile]
        Analyzed file snapshots in deterministic order.
    embedding_backend : repoindex.semantic.embeddings.EmbeddingBackendSpec
        Active embedding backend metadata.

    Returns
    -------
    int
        Total number of embeddings recomputed during persistence.
    """
    embeddings_recomputed = 0

    for _path, file_metadata_snapshot, analysis in parsed_files:
        embeddings_recomputed += sqlite_backend.persist_analysis(
            root,
            file_metadata=file_metadata_snapshot,
            analysis=analysis,
            embedding_backend=embedding_backend,
            conn=conn,
        )

    return embeddings_recomputed


def _collect_project_scan_state(
    root: Path,
    *,
    analyzers: list[LanguageAnalyzer],
) -> ProjectScanState:
    """
    Collect the current tracked file state used by index planning.

    Parameters
    ----------
    root : pathlib.Path
        Repository root being indexed.
    analyzers : list[repoindex.contracts.LanguageAnalyzer]
        Active analyzers available for file routing.

    Returns
    -------
    ProjectScanState
        Deterministic scan state for the current working tree.
    """
    analyzers_by_path = {
        str(path): _select_language_analyzer(path, analyzers)
        for path in sorted(iter_project_files(root, analyzers=analyzers))
    }
    metadata_by_path = {
        path: file_metadata(Path(path)) for path in sorted(analyzers_by_path)
    }
    return ProjectScanState(
        analyzers_by_path=analyzers_by_path,
        metadata_by_path=metadata_by_path,
        paths=sorted(metadata_by_path),
    )


def _load_existing_index_state(
    root: Path,
    *,
    sqlite_backend: SQLiteIndexBackend,
    embedding_backend: EmbeddingBackendSpec,
    conn: sqlite3.Connection,
) -> ExistingIndexState:
    """
    Load the persisted state needed for incremental index planning.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose index should be queried.
    sqlite_backend : repoindex.indexer.SQLiteIndexBackend
        Concrete backend providing the persisted state.
    embedding_backend : repoindex.semantic.embeddings.EmbeddingBackendSpec
        Active embedding backend metadata.
    conn : sqlite3.Connection
        Open backend connection reused across reads.

    Returns
    -------
    ExistingIndexState
        Deterministic persisted state used for reuse decisions.
    """
    file_hashes = sqlite_backend.load_existing_file_hashes(root, conn=conn)
    return ExistingIndexState(
        file_hashes=file_hashes,
        file_ownership=sqlite_backend.load_existing_file_ownership(
            root,
            conn=conn,
        ),
        paths=sorted(file_hashes),
        embedding_backend_matches=sqlite_backend.current_embedding_state_matches(
            root,
            embedding_backend=embedding_backend,
            conn=conn,
        ),
    )


def _plan_index_run(
    *,
    full: bool,
    current_state: ProjectScanState,
    existing_state: ExistingIndexState,
) -> IndexPlan:
    """
    Build the deterministic indexing plan for one repository pass.

    Parameters
    ----------
    full : bool
        Whether a full rebuild was requested.
    current_state : ProjectScanState
        Current tracked-file scan state.
    existing_state : ExistingIndexState
        Persisted index state used for reuse comparisons.

    Returns
    -------
    IndexPlan
        Planned indexed, reused, and deleted paths with stable reasons.
    """
    deleted_paths = [
        path
        for path in existing_state.paths
        if path not in current_state.metadata_by_path
    ]
    reused_paths: list[str] = []
    indexed_paths: list[str] = []
    decisions: list[IndexDecision] = []

    if full:
        indexed_paths = list(current_state.paths)
        for path in current_state.paths:
            decisions.append(IndexDecision(path, "indexed", "full rebuild requested"))
    else:
        for path in current_state.paths:
            existing_hash = existing_state.file_hashes.get(path)
            current_analyzer = current_state.analyzers_by_path[path]
            current_owner = (
                str(current_analyzer.name),
                str(current_analyzer.version),
            )
            current_hash = str(current_state.metadata_by_path[path]["hash"])
            if existing_hash is None:
                indexed_paths.append(path)
                decisions.append(IndexDecision(path, "indexed", "new file"))
            elif existing_hash != current_hash:
                indexed_paths.append(path)
                decisions.append(IndexDecision(path, "indexed", "file content changed"))
            elif existing_state.file_ownership.get(path) != current_owner:
                indexed_paths.append(path)
                decisions.append(
                    IndexDecision(
                        path,
                        "indexed",
                        "analyzer plugin or version changed",
                    )
                )
            elif not existing_state.embedding_backend_matches:
                indexed_paths.append(path)
                decisions.append(
                    IndexDecision(
                        path,
                        "indexed",
                        "embedding backend or version changed",
                    )
                )
            else:
                reused_paths.append(path)
                decisions.append(IndexDecision(path, "reused", "file hash unchanged"))

    for path in deleted_paths:
        decisions.append(IndexDecision(path, "deleted", "file removed"))

    return IndexPlan(
        indexed_paths=indexed_paths,
        reused_paths=reused_paths,
        deleted_paths=deleted_paths,
        decisions=decisions,
    )


def _prepare_index_storage(
    root: Path,
    *,
    full: bool,
    plan: IndexPlan,
    sqlite_backend: SQLiteIndexBackend,
    conn: sqlite3.Connection,
) -> None:
    """
    Delete persisted rows that the current index plan will replace.

    Parameters
    ----------
    root : pathlib.Path
        Repository root being indexed.
    full : bool
        Whether the current run is a full rebuild.
    plan : IndexPlan
        Deterministic indexing plan for the current run.
    sqlite_backend : repoindex.indexer.SQLiteIndexBackend
        Concrete backend receiving deletion requests.
    conn : sqlite3.Connection
        Open backend connection reused across writes.

    Returns
    -------
    None
        Persisted rows are removed in place before fresh analysis is stored.
    """
    if full:
        _clear_index_tables(conn)
        return

    sqlite_backend.delete_paths(
        root,
        paths=sorted(set(plan.indexed_paths) | set(plan.deleted_paths)),
        conn=conn,
    )


def _finalize_index_report(
    *,
    plan: IndexPlan,
    parsed_files: list[ParsedFile],
    failures: list[IndexFailure],
    warnings: list[IndexWarning],
    coverage_issues: list[CoverageIssue],
    embeddings_recomputed: int,
    embeddings_reused: int,
) -> IndexReport:
    """
    Build the deterministic report returned from one index run.

    Parameters
    ----------
    plan : IndexPlan
        Deterministic file-level plan executed during the run.
    parsed_files : list[ParsedFile]
        Successfully analyzed files persisted during the run.
    failures : list[IndexFailure]
        Per-file analysis failures collected during parsing.
    warnings : list[IndexWarning]
        Per-file analysis warnings collected during parsing.
    coverage_issues : list[CoverageIssue]
        Uncovered canonical-directory files detected during the run.
    embeddings_recomputed : int
        Number of embeddings written during persistence.
    embeddings_reused : int
        Number of existing embeddings preserved for reused files.

    Returns
    -------
    IndexReport
        Deterministic report sorted for stable rendering and tests.
    """
    decisions = sorted(
        plan.decisions,
        key=lambda decision: (
            decision.action,
            decision.path,
            decision.reason,
        ),
    )
    sorted_failures = sorted(
        failures,
        key=lambda failure: (
            failure.path,
            failure.analyzer_name,
            failure.error_type,
            failure.reason,
        ),
    )
    sorted_warnings = sorted(
        warnings,
        key=lambda warning: (
            warning.path,
            warning.analyzer_name,
            warning.warning_type,
            -1 if warning.line is None else warning.line,
            warning.reason,
        ),
    )
    return IndexReport(
        indexed=len(parsed_files),
        reused=len(plan.reused_paths),
        deleted=len(plan.deleted_paths),
        failed=len(sorted_failures),
        embeddings_recomputed=embeddings_recomputed,
        embeddings_reused=embeddings_reused,
        decisions=decisions,
        failures=sorted_failures,
        warnings=sorted_warnings,
        coverage_issues=coverage_issues,
    )


def index_repo(
    root: Path,
    *,
    full: bool = False,
) -> IndexReport:
    """
    Incrementally scan repository files and update the SQLite index.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose tracked analyzer-supported files should be
        indexed.
    full : bool, optional
        When ``True``, force a full rebuild instead of reusing unchanged files.

    Returns
    -------
    IndexReport
        Deterministic summary of the indexing run.
    """
    sqlite_backend = active_index_backend()
    analyzers = _active_language_analyzers()
    conn = sqlite_backend.open_connection(root)
    backend = get_embedding_backend()
    coverage_issues = _audit_canonical_directory_coverage(root, analyzers=analyzers)

    try:
        sqlite_backend.prune_orphaned_embeddings(root, conn=conn)
        current_state = _collect_project_scan_state(root, analyzers=analyzers)
        existing_state = _load_existing_index_state(
            root,
            sqlite_backend=sqlite_backend,
            embedding_backend=backend,
            conn=conn,
        )
        plan = _plan_index_run(
            full=full,
            current_state=current_state,
            existing_state=existing_state,
        )
        _prepare_index_storage(
            root,
            full=full,
            plan=plan,
            sqlite_backend=sqlite_backend,
            conn=conn,
        )

        embeddings_reused = (
            0
            if full
            else sqlite_backend.count_reusable_embeddings(
                root,
                paths=plan.reused_paths,
                conn=conn,
            )
        )

        parsed_files, failures, collected_warnings = _collect_indexed_file_analyses(
            root,
            plan.indexed_paths,
            current_state.metadata_by_path,
            analyzers,
        )
        embeddings_recomputed = _persist_indexed_file_analyses(
            root,
            conn=conn,
            sqlite_backend=sqlite_backend,
            parsed_files=parsed_files,
            embedding_backend=backend,
        )

        sqlite_backend.rebuild_derived_indexes(root, conn=conn)
        _persist_runtime_inventory(
            conn,
            backend_name=str(sqlite_backend.name),
            backend_version=str(sqlite_backend.version),
            coverage_complete=not coverage_issues,
            analyzers=analyzers,
        )
        conn.commit()

        return _finalize_index_report(
            plan=plan,
            parsed_files=parsed_files,
            failures=failures,
            warnings=collected_warnings,
            coverage_issues=coverage_issues,
            embeddings_recomputed=embeddings_recomputed,
            embeddings_reused=embeddings_reused,
        )
    finally:
        conn.close()
