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
from repoindex.query.context import context_for
from repoindex.query.exact import docstring_issues, find_call_edges, find_symbol
from repoindex.scanner import iter_project_files
from repoindex.schema import SCHEMA_VERSION
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
    parser = argparse.ArgumentParser(prog="repoindex")
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("help", help="Show help")
    sub.add_parser("index", help="Index repository")

    symbol_parser = sub.add_parser("symbol", help="Find symbol by exact name")
    symbol_parser.add_argument("name")

    calls_parser = sub.add_parser("calls", help="Inspect indexed static call edges")
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

    sub.add_parser("audit-docstrings", help="List docstring issues")

    context_parser = sub.add_parser(
        "context-for", help="Retrieve task-focused repository context"
    )
    context_parser.add_argument(
        "query", type=str, help="Natural-language query to retrieve context for"
    )
    context_parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON (agent mode)",
    )
    context_parser.add_argument(
        "--prompt",
        action="store_true",
        help="Output a Codex-ready deterministic prompt",
    )
    context_parser.add_argument(
        "--explain",
        action="store_true",
        help="Show retrieval routing and merge diagnostics",
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


def _run_index(root: Path) -> int:
    """
    Build or refresh the repository index.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose Python files should be indexed.

    Returns
    -------
    int
        Process exit status for a successful indexing run.
    """
    init_db(root)
    index_repo(root)

    commit = _get_head_commit(root)
    metadata = _read_index_metadata(root)
    metadata["schema_version"] = str(SCHEMA_VERSION)
    if commit:
        metadata["commit"] = commit
    _write_index_metadata(root, metadata)

    print("Repository indexed")
    return 0


def _run_symbol(root: Path, name: str) -> int:
    """
    Resolve and print exact symbol matches.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index.
    name : str
        Exact symbol name to look up.

    Returns
    -------
    int
        Zero when at least one symbol is found, otherwise one.
    """
    rows = find_symbol(root, name)

    if not rows:
        print(f"No symbol found: {name}")
        return 1

    for symbol_type, module_name, symbol_name, file_path, lineno in rows:
        if symbol_type == "module":
            print(f"{symbol_type}: {module_name} {file_path}:{lineno}")
        else:
            print(f"{symbol_type}: {module_name}.{symbol_name} {file_path}:{lineno}")

    return 0


def _run_audit_docstrings(root: Path) -> int:
    """
    Print indexed docstring issues.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the index.

    Returns
    -------
    int
        Process exit status for the audit command.
    """
    rows = docstring_issues(root)

    if not rows:
        print("No docstring issues found")
        return 0

    for issue_type, message in rows:
        print(f"{issue_type}: {message}")
    return 0


def _run_calls(
    root: Path,
    name: str,
    *,
    module: str | None,
    incoming: bool,
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
            cursor = conn.execute("SELECT COUNT(DISTINCT file_path) FROM symbol_index")
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

    if args.command in (None, "help"):
        return _run_help(parser)
    if args.command == "index":
        return _run_index(root)
    if args.command == "symbol":
        _ensure_index(root)
        return _run_symbol(root, args.name)
    if args.command == "calls":
        _ensure_index(root)
        return _run_calls(
            root,
            args.name,
            module=args.module,
            incoming=args.incoming,
        )
    if args.command == "audit-docstrings":
        _ensure_index(root)
        return _run_audit_docstrings(root)
    elif args.command == "context-for":
        _ensure_index(root)

        if args.prompt and args.explain:
            print("ERROR: --prompt and --explain cannot be used together")
            return 2

        result = context_for(
            root,
            args.query,
            as_json=args.json,
            as_prompt=args.prompt,
            explain=args.explain,
        )
        print(result)
        return 0

    parser.print_help()
    return 0
