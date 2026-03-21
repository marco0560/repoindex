#!/usr/bin/env python3
"""
Clean repository artifacts.

Removes git-ignored files from the working tree in a deterministic
and safe way.

This implementation is adapted from Fontshow and relies on Git as
the source of truth for what is removable.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

# Paths that should never be removed, even if ignored by git
PROTECTED_PATHS = {".venv", ".vscode", "node_modules", "src/repoindex/_version.py"}


def git_ignored_paths() -> Iterable[Path]:
    result = subprocess.run(
        ["git", "status", "--ignored", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )

    for line in result.stdout.splitlines():
        if line.startswith("!! "):
            yield Path(line[3:])


def remove_path(path: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"[DRY-RUN] Would remove: {path}")
        return

    if path.is_dir():
        shutil.rmtree(path)
        print(f"Removed directory: {path}")
    elif path.exists():
        path.unlink()
        print(f"Removed file: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean repository by removing ignored artifacts"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting anything",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()

    ignored = [
        path
        for path in git_ignored_paths()
        if path.parts and path.parts[0] not in PROTECTED_PATHS
    ]

    if not ignored:
        print("Nothing to clean.")
        return

    for path in ignored:
        remove_path(repo_root / path, dry_run=args.dry_run)

    if args.dry_run:
        print("\nDry-run completed.")
    else:
        print("\nDone.")


if __name__ == "__main__":
    main()
