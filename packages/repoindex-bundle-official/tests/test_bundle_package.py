"""Package-local tests for the first-party bundle distribution."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_bundle_package_declares_expected_first_party_dependencies() -> None:
    """Keep bundle metadata aligned to the curated first-party package set."""
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert project["project"]["dependencies"] == [
        "repoindex[semantic]",
        "repoindex-analyzer-python",
        "repoindex-analyzer-json",
        "repoindex-analyzer-c",
        "repoindex-analyzer-bash",
        "repoindex-backend-sqlite",
    ]
