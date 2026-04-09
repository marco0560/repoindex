#!/usr/bin/env python3
"""Build the repository's first-party packages from their package boundaries.

Responsibilities
----------------
- Define the deterministic build rehearsal for every first-party package directory.
- Print or execute the exact `python -m build` commands for the current checkout.
- Give the migration branch one local split-readiness gate before repositories are split.

Design principles
-----------------
The helper reuses the shared first-party package inventory and stays explicit
about command construction so package-boundary drift is easy to detect.

Architectural role
------------------
This script belongs to the **developer tooling layer** and supports Phase 3
multirepo readiness rehearsals.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.first_party_packages import package_paths

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_build_argv(*, python: str, package_path: Path) -> tuple[str, ...]:
    """
    Build the exact wheel+sdist command for one first-party package.

    Parameters
    ----------
    python : str
        Python interpreter used to run `build`.
    package_path : pathlib.Path
        First-party package directory to build.

    Returns
    -------
    tuple[str, ...]
        Deterministic command arguments for the build step.
    """
    return (
        python,
        "-m",
        "build",
        "--sdist",
        "--wheel",
        str(package_path),
    )


def build_all_argv(*, python: str, repo_root: Path) -> tuple[tuple[str, ...], ...]:
    """
    Build the command plan for every first-party package.

    Parameters
    ----------
    python : str
        Python interpreter used to run `build`.
    repo_root : pathlib.Path
        Repository root containing the package directories.

    Returns
    -------
    tuple[tuple[str, ...], ...]
        Build commands in deterministic first-party package order.
    """
    return tuple(
        build_build_argv(python=python, package_path=package_path)
        for package_path in package_paths(repo_root)
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments for the build rehearsal helper.

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
        description="Build repoindex first-party packages from the local checkout."
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to run `python -m build`.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved build commands without executing them.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Build the first-party package set for the local checkout.

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
    commands = build_all_argv(python=args.python, repo_root=REPO_ROOT)
    for command in commands:
        print(" ".join(command))
    if args.dry_run:
        return 0
    for command in commands:
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
