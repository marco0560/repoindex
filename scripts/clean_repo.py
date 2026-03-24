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
PROTECTED_PATHS = {
    Path(".venv"),
    Path(".vscode"),
    Path("node_modules"),
    Path("src/repoindex/_version.py"),
}


def git_ignored_paths() -> Iterable[Path]:
    """
    Yield Git-ignored paths reported by ``git status``.

    Returns
    -------
    collections.abc.Iterable[pathlib.Path]
        Ignored repository-relative paths.

    Raises
    ------
    subprocess.CalledProcessError
        If ``git status --ignored --porcelain`` fails.
    """
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
    """
    Remove a filesystem path or report the action in dry-run mode.

    Parameters
    ----------
    path : pathlib.Path
        File or directory path to remove.
    dry_run : bool
        Whether to print the planned action without mutating the filesystem.
    """
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
    """
    Remove ignored repository artifacts while preserving protected paths.
    """
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

    ignored = []

    for path in git_ignored_paths():
        if any(
            path == protected or protected in path.parents
            for protected in PROTECTED_PATHS
        ):
            continue
        ignored.append(path)

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
