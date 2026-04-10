#!/usr/bin/env python3
"""Install the repository's first-party package set.

Responsibilities
----------------
- Define the authoritative editable install set for first-party package-owned components.
- Run a deterministic editable-install plan for the current repository checkout.
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

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.first_party_packages import FIRST_PARTY_PACKAGE_DIRS, package_paths

REPO_ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY_EDITABLE_PACKAGES = FIRST_PARTY_PACKAGE_DIRS
BUNDLE_PACKAGE_DIR = "packages/repoindex-bundle-official"


def editable_core_requirement(
    repo_root: Path,
    *,
    extras: tuple[str, ...] = (),
) -> str:
    """
    Return the editable requirement string for the core package.

    Parameters
    ----------
    repo_root : pathlib.Path
        Repository root containing the core ``repoindex`` package.
    extras : tuple[str, ...], optional
        Optional extras requested on the core editable install.

    Returns
    -------
    str
        Editable requirement string for the core package, including extras when
        requested.
    """
    if not extras:
        return str(repo_root)
    return f"{repo_root}[{','.join(extras)}]"


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
    return package_paths(repo_root)


def bundle_package_path(repo_root: Path) -> Path:
    """
    Return the editable bundle package path for the repository.

    Parameters
    ----------
    repo_root : pathlib.Path
        Repository root that owns the first-party packages.

    Returns
    -------
    pathlib.Path
        Bundle package directory resolved from ``repo_root``.
    """
    return repo_root / BUNDLE_PACKAGE_DIR


def non_bundle_package_paths(repo_root: Path) -> tuple[Path, ...]:
    """
    Return editable first-party package paths excluding the bundle package.

    Parameters
    ----------
    repo_root : pathlib.Path
        Repository root that owns the first-party packages.

    Returns
    -------
    tuple[pathlib.Path, ...]
        Editable package directories except the curated bundle package.
    """
    return tuple(
        package_path
        for package_path in editable_package_paths(repo_root)
        if package_path != bundle_package_path(repo_root)
    )


def build_install_commands(
    *,
    python: str,
    repo_root: Path,
    include_core: bool = False,
    core_extras: tuple[str, ...] = (),
) -> tuple[tuple[str, ...], ...]:
    """
    Build the exact pip-install command plan for first-party packages.

    Parameters
    ----------
    python : str
        Python interpreter used to run `pip`.
    repo_root : pathlib.Path
        Repository root containing the package directories.
    include_core : bool, optional
        Whether to include the editable core ``repoindex`` package before the
        first-party package set.
    core_extras : tuple[str, ...], optional
        Optional extras requested on the editable core install.

    Returns
    -------
    tuple[tuple[str, ...], ...]
        Deterministic install commands for the source-tree package set.
    """
    editable_install_argv: list[str] = [python, "-m", "pip", "install"]
    if include_core:
        editable_install_argv.extend(
            (
                "-e",
                editable_core_requirement(repo_root, extras=core_extras),
            )
        )
    for package_path in non_bundle_package_paths(repo_root):
        editable_install_argv.extend(("-e", str(package_path)))

    bundle_install_argv = (
        python,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "-e",
        str(bundle_package_path(repo_root)),
    )
    return (tuple(editable_install_argv), bundle_install_argv)


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
        "--include-core",
        action="store_true",
        help="Include the editable core repoindex package in the install command.",
    )
    parser.add_argument(
        "--core-extra",
        dest="core_extras",
        action="append",
        default=[],
        help="Optional extra requested on the editable core install. Repeat as needed.",
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
    commands = build_install_commands(
        python=args.python,
        repo_root=REPO_ROOT,
        include_core=args.include_core,
        core_extras=tuple(args.core_extras),
    )
    for command in commands:
        print(" ".join(command))
    if args.dry_run:
        return 0
    for command in commands:
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
