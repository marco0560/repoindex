from __future__ import annotations

import argparse
from pathlib import Path

from repoindex.indexer import index_repo
from repoindex.query.context import context_for
from repoindex.query.exact import docstring_issues, find_symbol
from repoindex.storage import init_db


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repoindex")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("help", help="Show help")
    sub.add_parser("index", help="Index repository")

    symbol_parser = sub.add_parser("symbol", help="Find symbol by exact name")
    symbol_parser.add_argument("name")

    sub.add_parser("audit-docstrings", help="List docstring issues")

    context_parser = sub.add_parser("context-for")
    context_parser.add_argument("query", type=str)

    return parser


def _run_help(parser: argparse.ArgumentParser) -> int:
    parser.print_help()
    return 0


def _run_index() -> int:
    root = Path.cwd()
    init_db(root)
    index_repo(root)
    print("Repository indexed")
    return 0


def _run_symbol(name: str) -> int:
    root = Path.cwd()
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


def _run_audit_docstrings() -> int:
    root = Path.cwd()
    rows = docstring_issues(root)

    if not rows:
        print("No docstring issues found")
        return 0

    for issue_type, message in rows:
        print(f"{issue_type}: {message}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in (None, "help"):
        return _run_help(parser)
    if args.command == "index":
        return _run_index()
    if args.command == "symbol":
        return _run_symbol(args.name)
    if args.command == "audit-docstrings":
        return _run_audit_docstrings()
    elif args.command == "context-for":
        result = context_for(Path.cwd(), args.query)
        print(result)
        return 0

    parser.print_help()
    return 0
