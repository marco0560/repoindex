#!/usr/bin/env python3
"""Install the repository's first-party package set.

Responsibilities
----------------
- Define the authoritative editable install set for first-party package-owned components.
- Run one deterministic `pip install -e ...` command for the current repository checkout.
- Keep bootstrap, CI, and maintainer workflows aligned to the same package list.

Design principles
-----------------
The script centralizes package ownership metadata so first-party install flows
do not drift across bootstrap commands, CI jobs, and local maintenance docs.

Architectural role
------------------
This script belongs to the **developer tooling layer** and enforces the
repository-local first-party package boundary accepted in ADR-007.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY_EDITABLE_PACKAGES: tuple[str, ...] = (
    "packages/repoindex-analyzer-python",
    "packages/repoindex-analyzer-json",
    "packages/repoindex-analyzer-c",
    "packages/repoindex-analyzer-bash",
    "packages/repoindex-bundle-official",
)


def editable_package_paths(repo_root: Path) -> tuple[Path, ...]:
    """
    Return the authoritative editable package paths for the repository.

    Parameters
    ----------
    repo_root : pathlib.Path
        Repository root that owns the first-party packages.

    Returns
    -------
    tuple[pathlib.Path, ...]
        Editable package directories in deterministic install order.
    """
    return tuple(repo_root / relative for relative in FIRST_PARTY_EDITABLE_PACKAGES)


def build_install_argv(*, python: str, repo_root: Path) -> tuple[str, ...]:
    """
    Build the exact pip-install command for first-party packages.

    Parameters
    ----------
    python : str
        Python interpreter used to run `pip`.
    repo_root : pathlib.Path
        Repository root containing the package directories.

    Returns
    -------
    tuple[str, ...]
        Deterministic command arguments for the install step.
    """
    argv: list[str] = [python, "-m", "pip", "install"]
    for package_path in editable_package_paths(repo_root):
        argv.extend(("-e", str(package_path)))
    return tuple(argv)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments for the install helper.

    Parameters
    ----------
    argv : list[str] | None, optional
        Optional argument override.

    Returns
    -------
    argparse.Namespace
        Parsed helper arguments.
    """
    parser = argparse.ArgumentParser(
        description="Install repoindex first-party packages from the local checkout."
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to run `pip install`.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved command without executing it.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Install the first-party package set for the local checkout.

    Parameters
    ----------
    argv : list[str] | None, optional
        Optional argument override.

    Returns
    -------
    int
        Process exit code.
    """
    args = parse_args(argv)
    command = build_install_argv(python=args.python, repo_root=REPO_ROOT)
    print(" ".join(command))
    if args.dry_run:
        return 0
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
