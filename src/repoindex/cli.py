"""Command-line entry points for repoindex."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from repoindex._version import version as __version__
from repoindex.indexer import index_repo
from repoindex.prefix import normalize_prefix
from repoindex.query.context import context_for
from repoindex.query.exact import (
    docstring_issues,
    embedding_inventory,
    find_call_edges,
    find_callable_refs,
    find_symbol,
)
from repoindex.scanner import iter_project_files
from repoindex.schema import SCHEMA_VERSION
from repoindex.semantic.embeddings import get_embedding_backend
from repoindex.semantic.search import embedding_candidates
from repoindex.storage import get_db_path, get_repoindex_dir, init_db


def build_parser() -> argparse.ArgumentParser:
    """
    Build the top-level command-line parser.

    Parameters
    ----------
    None

    Returns
    -------
    argparse.ArgumentParser
        Parser configured with the supported repoindex subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="repoindex",
        description=(
            "Index a repository, precompute semantic embeddings, inspect exact "
            "symbols and static relations, and retrieve task-focused context."
        ),
        epilog=(
            "Examples:\n"
            "  repoindex index\n"
            '  repoindex context-for "find schema migration logic"\n'
            "  repoindex context-for --prompt "
            '"add a regression test for symbol lookup"\n'
            '  repoindex context-for "schema migration rules"\n'
            '  repoindex embeddings "schema migration rules"\n'
            "  repoindex calls caller\n"
            "  repoindex refs _retrieve_script_candidates --incoming\n"
            "  repoindex calls imported_helper --module pkg.b --incoming"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(
        dest="command",
        title="subcommands",
        metavar=(
            "{help,index,symbol,embeddings,calls,refs,audit-docstrings," "context-for}"
        ),
    )

    sub.add_parser("help", help="Show help")
    index_parser = sub.add_parser(
        "index",
        help="Build or refresh the repository index",
        description=(
            "Build the repository-local SQLite index used by repoindex queries, "
            "including precomputed semantic embeddings. Incremental indexing "
            "reuses unchanged files by default."
        ),
        epilog=(
            "Examples:\n"
            "  repoindex index\n"
            "  repoindex index --explain\n"
            "  repoindex index --full"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    index_parser.add_argument(
        "--full",
        action="store_true",
        help="Force a full rebuild instead of reusing unchanged files",
    )
    index_parser.add_argument(
        "--explain",
        "--verbose",
        dest="explain",
        action="store_true",
        help="Show per-file indexing decisions after the summary",
    )

    symbol_parser = sub.add_parser(
        "symbol",
        help="Find symbol by exact name",
        description="Resolve one exact symbol name from the indexed repository.",
        epilog=(
            "Examples:\n"
            "  repoindex symbol build_parser\n"
            "  repoindex symbol build_parser --prefix src/repoindex"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    symbol_parser.add_argument("name", help="Exact symbol name to look up")
    symbol_parser.add_argument(
        "--prefix",
        help="Restrict results to files under this repo-root-relative path prefix",
    )

    embeddings_parser = sub.add_parser(
        "embeddings",
        help="Inspect embedding-channel matches",
        description=(
            "Inspect the active embedding backend and show top embedding-only "
            "matches for a natural-language query."
        ),
        epilog=(
            "Examples:\n"
            '  repoindex embeddings "schema migration rules"\n'
            '  repoindex embeddings "numpy docstring sections" --limit 3\n'
            '  repoindex embeddings "numpy docstring sections" --prefix '
            "src/repoindex/query"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    embeddings_parser.add_argument(
        "query",
        help="Natural-language query to score against stored embeddings",
    )
    embeddings_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of embedding matches to print",
    )
    embeddings_parser.add_argument(
        "--prefix",
        help="Restrict matches to files under this repo-root-relative path prefix",
    )

    calls_parser = sub.add_parser(
        "calls",
        help="Inspect indexed static call edges",
        description=(
            "Inspect static heuristic call edges stored during indexing. "
            "Use --incoming to show callers of a callee."
        ),
        epilog=(
            "Examples:\n"
            "  repoindex calls caller\n"
            "  repoindex calls caller --prefix src/repoindex/query\n"
            "  repoindex calls imported_helper --module pkg.b --incoming"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    calls_parser.add_argument(
        "name",
        help="Exact logical caller or callee name to inspect",
    )
    calls_parser.add_argument(
        "--module",
        help="Restrict the caller or callee side to one exact module",
    )
    calls_parser.add_argument(
        "--incoming",
        action="store_true",
        help="Show callers of the named callee instead of outgoing edges",
    )
    calls_parser.add_argument(
        "--prefix",
        help="Restrict caller files to this repo-root-relative path prefix",
    )

    refs_parser = sub.add_parser(
        "refs",
        help="Inspect indexed callable-object references",
        description=(
            "Inspect static heuristic references to callable objects such as "
            "registry bindings, return values, and assignment values. "
            "Use --incoming to show owners that reference a target."
        ),
        epilog=(
            "Examples:\n"
            "  repoindex refs helper\n"
            "  repoindex refs helper --prefix src/repoindex/query\n"
            "  repoindex refs _retrieve_script_candidates --incoming\n"
            "  repoindex refs imported_helper --module pkg.b --incoming"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    refs_parser.add_argument(
        "name",
        help="Exact logical owner or target name to inspect",
    )
    refs_parser.add_argument(
        "--module",
        help="Restrict the owner or target side to one exact module",
    )
    refs_parser.add_argument(
        "--incoming",
        action="store_true",
        help="Show owners of the named target instead of outgoing references",
    )
    refs_parser.add_argument(
        "--prefix",
        help="Restrict owner files to this repo-root-relative path prefix",
    )

    audit_parser = sub.add_parser(
        "audit-docstrings",
        help="List docstring issues",
        description="Print indexed docstring issues in deterministic order.",
        epilog=(
            "Examples:\n"
            "  repoindex audit-docstrings\n"
            "  repoindex audit-docstrings --prefix src/repoindex/query"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    audit_parser.add_argument(
        "--prefix",
        help="Restrict issues to files under this repo-root-relative path prefix",
    )

    context_parser = sub.add_parser(
        "context-for",
        help="Retrieve task-focused repository context",
        description=(
            "Retrieve task-focused repository context for a natural-language "
            "query. The retrieval pipeline includes symbol, heuristic semantic, "
            "and embedding channels. Output modes are mutually exclusive."
        ),
        epilog=(
            "Examples:\n"
            '  repoindex context-for "find schema migration logic"\n'
            '  repoindex context-for "find schema migration logic" --prefix '
            "src/repoindex/query\n"
            '  repoindex context-for "schema migration rules"\n'
            '  repoindex context-for --json "static call graph"\n'
            '  repoindex context-for --prompt "add a test for imported calls"\n'
            "  repoindex context-for --explain "
            '"why does symbol lookup rank this result?"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    context_parser.add_argument(
        "query", type=str, help="Natural-language query to retrieve context for"
    )
    mode_group = context_parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON (agent mode)",
    )
    mode_group.add_argument(
        "--prompt",
        action="store_true",
        help="Output a Codex-ready deterministic prompt",
    )
    mode_group.add_argument(
        "--explain",
        action="store_true",
        help="Show retrieval routing and merge diagnostics",
    )
    context_parser.add_argument(
        "--prefix",
        help="Restrict retrieval to files under this repo-root-relative path prefix",
    )

    return parser


def _run_help(parser: argparse.ArgumentParser) -> int:
    """
    Print CLI help text.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Parser whose help message should be rendered.

    Returns
    -------
    int
        Process exit status for a successful help invocation.
    """
    parser.print_help()
    return 0


def _run_index(root: Path, *, full: bool, explain: bool) -> int:
    """
    Build or refresh the repository index.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose Python files should be indexed.
    full : bool
        Whether to force a full rebuild instead of incremental reuse.
    explain : bool
        Whether to print per-file indexing decisions after the summary.

    Returns
    -------
    int
        Process exit status for a successful indexing run.
    """
    init_db(root)
    report = index_repo(root, full=full)

    commit = _get_head_commit(root)
    metadata = _read_index_metadata(root)
    metadata["schema_version"] = str(SCHEMA_VERSION)
    if commit:
        metadata["commit"] = commit
    _write_index_metadata(root, metadata)

    print(f"Indexed: {report.indexed}")
    print(f"Reused: {report.reused}")
    print(f"Deleted: {report.deleted}")
    print(f"Embeddings recomputed: {report.embeddings_recomputed}")
    print(f"Embeddings reused: {report.embeddings_reused}")
    if explain:
        for decision in report.decisions:
            rel_path = Path(decision.path)
            try:
                rel_label = rel_path.relative_to(root).as_posix()
            except ValueError:
                rel_label = decision.path
            print(f"{decision.action}: {rel_label} ({decision.reason})")
    return 0


def _run_symbol(root: Path, name: str, *, prefix: str | None = None) -> int:
    """
    Resolve and print exact symbol matches.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index.
    name : str
        Exact symbol name to look up.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict symbol files.

    Returns
    -------
    int
        Zero when at least one symbol is found, otherwise one.
    """
    rows = find_symbol(root, name, prefix=prefix)

    if not rows:
        print(f"No symbol found: {name}")
        return 1

    for symbol_type, module_name, symbol_name, file_path, lineno in rows:
        if symbol_type == "module":
            print(f"{symbol_type}: {module_name} {file_path}:{lineno}")
        else:
            print(f"{symbol_type}: {module_name}.{symbol_name} {file_path}:{lineno}")

    return 0


def _run_audit_docstrings(root: Path, *, prefix: str | None = None) -> int:
    """
    Print indexed docstring issues.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict issue ownership.

    Returns
    -------
    int
        Process exit status for the audit command.
    """
    rows = docstring_issues(root, prefix=prefix)

    if not rows:
        print("No docstring issues found")
        return 0

    for issue_type, message in rows:
        print(f"{issue_type}: {message}")
    return 0


def _run_embeddings(
    root: Path,
    query: str,
    *,
    limit: int,
    prefix: str | None = None,
) -> int:
    """
    Print embedding-backend metadata and top embedding matches.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index.
    query : str
        Natural-language query to score.
    limit : int
        Maximum number of matches to print.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict matched files.

    Returns
    -------
    int
        Zero when embedding inventory exists, otherwise one.
    """
    backend = get_embedding_backend()
    inventory = embedding_inventory(root)

    if not inventory:
        print("No stored embeddings found. Run: repoindex index")
        return 1

    print(
        "backend:"
        f" {backend.name}"
        f" version={backend.version}"
        f" dim={backend.dim}"
    )
    for stored_backend, stored_version, stored_dim, count in inventory:
        print(
            "stored:"
            f" {stored_backend}"
            f" version={stored_version}"
            f" dim={stored_dim}"
            f" rows={count}"
        )

    matches = embedding_candidates(
        root,
        query,
        limit=limit,
        min_score=0.0,
        prefix=prefix,
    )
    if not matches:
        print("No embedding matches found.")
        return 0

    for score, (symbol_type, module_name, name, file_path, lineno) in matches:
        print(f"{score:.2f} {symbol_type}: {module_name}.{name} {file_path}:{lineno}")

    return 0


def _run_calls(
    root: Path,
    name: str,
    *,
    module: str | None,
    incoming: bool,
    prefix: str | None = None,
) -> int:
    """
    Print indexed static call edges for one logical name.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index.
    name : str
        Exact logical caller or callee name to inspect.
    module : str | None
        Optional exact module filter for the selected side of the edge.
    incoming : bool
        Whether to show incoming edges for a callee instead of outgoing edges
        for a caller.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict caller files.

    Returns
    -------
    int
        Zero when at least one edge is found, otherwise one.
    """
    rows = find_call_edges(
        root,
        name,
        module=module,
        incoming=incoming,
        prefix=prefix,
    )

    if not rows:
        direction = "callee" if incoming else "caller"
        if module is None:
            print(f"No call edges found for {direction}: {name}")
        else:
            print(f"No call edges found for {direction}: {module}.{name}")
        return 1

    for caller_module, caller_name, callee_module, callee_name, resolved in rows:
        caller = f"{caller_module}.{caller_name}"
        if resolved:
            assert callee_module is not None
            assert callee_name is not None
            callee = f"{callee_module}.{callee_name}"
        else:
            callee = "<unresolved>"
        print(f"{caller} -> {callee}")

    return 0


def _run_refs(
    root: Path,
    name: str,
    *,
    module: str | None,
    incoming: bool,
    prefix: str | None = None,
) -> int:
    """
    Print indexed callable-object references for one logical name.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index.
    name : str
        Exact logical owner or referenced target name to inspect.
    module : str | None
        Optional exact module filter for the selected side of the reference.
    incoming : bool
        Whether to show incoming references for a target instead of outgoing
        references for an owner.
    prefix : str | None, optional
        Repo-root-relative path prefix used to restrict owner files.

    Returns
    -------
    int
        Zero when at least one reference is found, otherwise one.
    """
    rows = find_callable_refs(
        root,
        name,
        module=module,
        incoming=incoming,
        prefix=prefix,
    )

    if not rows:
        direction = "target" if incoming else "owner"
        if module is None:
            print(f"No callable references found for {direction}: {name}")
        else:
            print(f"No callable references found for {direction}: {module}.{name}")
        return 1

    for owner_module, owner_name, target_module, target_name, resolved in rows:
        owner = f"{owner_module}.{owner_name}"
        if resolved:
            assert target_module is not None
            assert target_name is not None
            target = f"{target_module}.{target_name}"
        else:
            target = "<unresolved>"
        print(f"{owner} => {target}")

    return 0


def _get_head_commit(root: Path) -> str | None:
    """
    Read the current Git commit hash for a repository.

    Parameters
    ----------
    root : pathlib.Path
        Repository root used as the subprocess working directory.

    Returns
    -------
    str | None
        Current ``HEAD`` commit hash, or ``None`` if it cannot be read.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _read_index_metadata(root: Path) -> dict[str, str]:
    """
    Load persisted index metadata.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the ``.repoindex`` directory.

    Returns
    -------
    dict[str, str]
        Parsed metadata values, or an empty mapping when the metadata file
        does not exist or cannot be decoded.
    """
    path = get_repoindex_dir(root) / "metadata.json"
    if not path.exists():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {}


def _write_index_metadata(root: Path, data: dict[str, str]) -> None:
    """
    Persist index metadata as JSON.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the ``.repoindex`` directory.
    data : dict[str, str]
        Metadata payload to serialize.

    Returns
    -------
    None
        The metadata file is written in place.
    """
    path = get_repoindex_dir(root) / "metadata.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _resolve_prefix_argument(
    parser: argparse.ArgumentParser,
    root: Path,
    prefix: str | None,
) -> str | None:
    """
    Normalize one CLI prefix argument or terminate with a parser error.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Active top-level parser used for error reporting.
    root : pathlib.Path
        Repository root that anchors the prefix.
    prefix : str | None
        User-supplied repo-root-relative prefix.

    Returns
    -------
    str | None
        Absolute normalized prefix path, or ``None`` when unset.
    """
    if prefix is not None and Path(prefix).is_absolute():
        parser.error("Prefix must be relative to the repository root.")
    try:
        return normalize_prefix(root, prefix)
    except ValueError as exc:
        parser.error(str(exc))
        return None


def _ensure_index(root: Path) -> None:
    """
    Ensure that the repository index exists and is usable.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose local index should be checked.

    Returns
    -------
    None
        The function returns after confirming or rebuilding the index.

    Raises
    ------
    SystemExit
        If the index cannot be built or is corrupted and unreadable.

    Notes
    -----
    If the on-disk index is missing or stale, the function rebuilds it
    automatically and refreshes the stored Git commit metadata.
    """
    db_path = get_db_path(root)

    # --- CASE 1: missing DB → auto-index ---
    if not db_path.exists():
        print("[repoindex] Index not found — building it now...")
        try:
            init_db(root)
            index_repo(root)
            commit = _get_head_commit(root)
            if commit:
                _write_index_metadata(root, {"commit": commit})
        except Exception as e:
            print("ERROR: failed to build index automatically")
            print("Run manually: repoindex index")
            print(f"Details: {e}")
            raise SystemExit(1)

        print("[repoindex] Index ready", file=sys.stderr)
        return

    # --- CASE 2: DB exists → canary check ---
    try:
        conn = sqlite3.connect(db_path)
        try:
            # Basic canary
            conn.execute("SELECT 1")

            # Schema canary (minimal, non-invasive)
            # We expect at least one known table; adjust if needed
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
            )
            if cursor.fetchone() is None:
                raise RuntimeError("empty or invalid database schema")

            # --- GIT STALENESS CHECK ---
            current_commit = _get_head_commit(root)
            metadata = _read_index_metadata(root)
            indexed_commit = metadata.get("commit")
            indexed_schema = metadata.get("schema_version")

            if indexed_schema != str(SCHEMA_VERSION):
                print(
                    "[repoindex] Index schema changed — rebuilding...",
                    file=sys.stderr,
                )
                conn.close()
                init_db(root)
                index_repo(root)
                commit = _get_head_commit(root)
                metadata = {"schema_version": str(SCHEMA_VERSION)}
                if commit:
                    metadata["commit"] = commit
                _write_index_metadata(root, metadata)
                print("[repoindex] Index ready", file=sys.stderr)
                return

            if current_commit and indexed_commit != current_commit:
                print(
                    "[repoindex] Index outdated (git commit changed) — rebuilding...",
                    file=sys.stderr,
                )
                conn.close()
                init_db(root)
                index_repo(root)

                _write_index_metadata(
                    root,
                    {
                        "commit": current_commit,
                        "schema_version": str(SCHEMA_VERSION),
                    },
                )

                print("[repoindex] Index ready", file=sys.stderr)
                return

            # --- STALENESS CHECK: file count mismatch ---
            cursor = conn.execute("SELECT COUNT(DISTINCT file_id) FROM symbol_index")
            indexed_files = cursor.fetchone()[0]

            current_files = len(list(iter_project_files(root)))

            if indexed_files != current_files:
                print("[repoindex] Index stale — rebuilding...", file=sys.stderr)
                conn.close()
                init_db(root)
                index_repo(root)
                commit = _get_head_commit(root)
                metadata = {"schema_version": str(SCHEMA_VERSION)}
                if commit:
                    metadata["commit"] = commit
                _write_index_metadata(root, metadata)
                print("[repoindex] Index ready", file=sys.stderr)
                return

        finally:
            conn.close()

    except Exception as e:
        print("ERROR: repository index is corrupted or unreadable")
        print("Suggested fix: repoindex index")
        print(f"Details: {e}")
        raise SystemExit(1)


def main() -> int:
    """
    Dispatch the repoindex command-line interface.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Process exit status for the selected subcommand.
    """
    parser = build_parser()
    args = parser.parse_args()
    root = Path.cwd()
    prefix = _resolve_prefix_argument(parser, root, getattr(args, "prefix", None))

    if args.command in (None, "help"):
        return _run_help(parser)
    if args.command == "index":
        return _run_index(root, full=args.full, explain=args.explain)
    if args.command == "symbol":
        _ensure_index(root)
        return _run_symbol(root, args.name, prefix=prefix)
    if args.command == "embeddings":
        _ensure_index(root)
        return _run_embeddings(root, args.query, limit=args.limit, prefix=prefix)
    if args.command == "calls":
        _ensure_index(root)
        return _run_calls(
            root,
            args.name,
            module=args.module,
            incoming=args.incoming,
            prefix=prefix,
        )
    if args.command == "refs":
        _ensure_index(root)
        return _run_refs(
            root,
            args.name,
            module=args.module,
            incoming=args.incoming,
            prefix=prefix,
        )
    if args.command == "audit-docstrings":
        _ensure_index(root)
        return _run_audit_docstrings(root, prefix=prefix)
    elif args.command == "context-for":
        _ensure_index(root)

        result = context_for(
            root,
            args.query,
            prefix=prefix,
            as_json=args.json,
            as_prompt=args.prompt,
            explain=args.explain,
        )
        print(result)
        return 0

    parser.print_help()
    return 0
