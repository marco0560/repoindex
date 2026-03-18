from __future__ import annotations

import argparse
from pathlib import Path

from repoindex.storage import init_db


def main() -> int:
    parser = argparse.ArgumentParser(prog="repoindex")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("index", help="Initialize repository index")

    args = parser.parse_args()

    if args.command == "index":
        root = Path.cwd()
        init_db(root)
        print("Initialized .repoindex database")
        return 0

    parser.print_help()
    return 1
