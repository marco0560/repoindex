#!/usr/bin/env python3
"""Define file-ownership manifests for the future multirepo split.

Responsibilities
----------------
- Record the deterministic path ownership for each future repository in the accepted split topology.
- Keep the actual repository extraction step grounded in a reviewed file manifest rather than an informal checklist.
- Provide one source of truth for split planning docs and regression tests.

Design principles
-----------------
The manifest stays declarative, path-based, and explicit so repository extraction can be reviewed and executed mechanically.

Architectural role
------------------
This script belongs to the **developer tooling layer** and prepares the concrete file movement needed for Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FutureRepoSplitManifest:
    """
    Declarative path manifest for one future repository.

    Parameters
    ----------
    repository : str
        Future repository name.
    owned_paths : tuple[str, ...]
        Repository-relative paths that should move into the future repository.
    stays_in_core : tuple[str, ...]
        Repository-relative paths that remain owned by the core repo but are
        operationally relevant to the future repository.
    """

    repository: str
    owned_paths: tuple[str, ...]
    stays_in_core: tuple[str, ...]


def future_repo_split_manifests() -> tuple[FutureRepoSplitManifest, ...]:
    """
    Return the accepted path manifests for the future split repositories.

    Parameters
    ----------
    None

    Returns
    -------
    tuple[FutureRepoSplitManifest, ...]
        Split manifests in deterministic repository order.
    """
    return (
        FutureRepoSplitManifest(
            repository="repoindex",
            owned_paths=(
                ".gitignore",
                ".github/workflows/ci.yml",
                ".github/workflows/commit-message-check.yml",
                ".github/workflows/docs.yml",
                ".github/workflows/release.yml",
                ".pre-commit-config.yaml",
                ".releaserc.json",
                "LICENSE",
                "README.md",
                "docs/",
                "examples/",
                "mkdocs.yml",
                "package-lock.json",
                "package.json",
                "pyproject.toml",
                "scripts/",
                "src/repoindex/",
                "tests/",
            ),
            stays_in_core=(),
        ),
        FutureRepoSplitManifest(
            repository="repoindex-analyzer-python",
            owned_paths=(
                "packages/repoindex-analyzer-python/README.md",
                "packages/repoindex-analyzer-python/pyproject.toml",
                "packages/repoindex-analyzer-python/src/",
                "packages/repoindex-analyzer-python/tests/",
            ),
            stays_in_core=(
                "src/repoindex/analyzers/python.py",
                "tests/test_plugins.py",
            ),
        ),
        FutureRepoSplitManifest(
            repository="repoindex-analyzer-json",
            owned_paths=(
                "packages/repoindex-analyzer-json/README.md",
                "packages/repoindex-analyzer-json/pyproject.toml",
                "packages/repoindex-analyzer-json/src/",
                "packages/repoindex-analyzer-json/tests/",
            ),
            stays_in_core=(
                "src/repoindex/analyzers/json.py",
                "tests/test_plugins.py",
            ),
        ),
        FutureRepoSplitManifest(
            repository="repoindex-analyzer-c",
            owned_paths=(
                "packages/repoindex-analyzer-c/README.md",
                "packages/repoindex-analyzer-c/pyproject.toml",
                "packages/repoindex-analyzer-c/src/",
                "packages/repoindex-analyzer-c/tests/",
            ),
            stays_in_core=(
                "src/repoindex/analyzers/c.py",
                "tests/test_plugins.py",
            ),
        ),
        FutureRepoSplitManifest(
            repository="repoindex-analyzer-bash",
            owned_paths=(
                "packages/repoindex-analyzer-bash/README.md",
                "packages/repoindex-analyzer-bash/pyproject.toml",
                "packages/repoindex-analyzer-bash/src/",
                "packages/repoindex-analyzer-bash/tests/",
            ),
            stays_in_core=(
                "src/repoindex/analyzers/bash.py",
                "tests/test_plugins.py",
            ),
        ),
        FutureRepoSplitManifest(
            repository="repoindex-backend-sqlite",
            owned_paths=(
                "packages/repoindex-backend-sqlite/README.md",
                "packages/repoindex-backend-sqlite/pyproject.toml",
                "packages/repoindex-backend-sqlite/src/",
                "packages/repoindex-backend-sqlite/tests/",
            ),
            stays_in_core=(
                "src/repoindex/indexer.py",
                "src/repoindex/sqlite_backend_support.py",
                "tests/test_plugins.py",
            ),
        ),
        FutureRepoSplitManifest(
            repository="repoindex-bundle-official",
            owned_paths=(
                "packages/repoindex-bundle-official/README.md",
                "packages/repoindex-bundle-official/pyproject.toml",
                "packages/repoindex-bundle-official/tests/",
            ),
            stays_in_core=("tests/test_plugins.py",),
        ),
    )
