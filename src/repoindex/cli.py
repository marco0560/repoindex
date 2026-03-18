from __future__ import annotations

import argparse
from pathlib import Path

from repoindex.indexer import index_repo
from repoindex.storage import init_db


def main() -> int:
    parser = argparse.ArgumentParser(prog="repoindex")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("index", help="Index repository")

    args = parser.parse_args()

    if args.command == "index":
        root = Path.cwd()
        init_db(root)
        index_repo(root)
        print("Repository indexed")
        return 0

    parser.print_help()
    return 1
