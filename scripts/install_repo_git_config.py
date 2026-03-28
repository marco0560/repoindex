#!/usr/bin/env python3
"""Install deterministic repo-local Git configuration."""

from __future__ import annotations

import subprocess


def git_alias_entries() -> list[tuple[str, str]]:
    """
    Return repo-local Git config entries to install.

    Parameters
    ----------
    None

    Returns
    -------
    list[tuple[str, str]]
        Ordered ``(key, value)`` Git config entries.
    """

    return [
        ("core.hooksPath", ".githooks"),
        ("commit.template", ".gitmessage"),
        ("pull.ff", "only"),
        ("pull.rebase", "false"),
        ("rebase.autostash", "true"),
        (
            "alias.clean-repo",
            "!bash scripts/run_with_repo_python.sh scripts/clean_repo.py",
        ),
        (
            "alias.ctx",
            (
                "!f(){ bash scripts/run_with_repo_python.sh -m repoindex "
                'context-for "$@"; }; f'
            ),
        ),
        (
            "alias.check",
            (
                "!bash -lc 'source .venv/bin/activate && black --check . && "
                "ruff check . && mypy . && pytest'"
            ),
        ),
        (
            "alias.bootstrap",
            (
                "!bash scripts/run_with_repo_python.sh "
                "scripts/bootstrap_dev_environment.py"
            ),
        ),
        (
            "alias.install-repo-config",
            (
                "!bash scripts/run_with_repo_python.sh "
                "scripts/install_repo_git_config.py"
            ),
        ),
        (
            "alias.docs-build",
            "!bash -lc 'source .venv/bin/activate && mkdocs build --strict'",
        ),
    ]


def main() -> int:
    """
    Apply the repo-local Git configuration entries.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Process exit code.
    """

    for key, value in git_alias_entries():
        subprocess.run(["git", "config", "--local", key, value], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
