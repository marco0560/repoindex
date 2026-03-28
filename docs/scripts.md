# Scripts

## `scripts/bootstrap_dev_environment.py`

Create `.venv`, install development and documentation dependencies, install
repo-local Git configuration, and optionally run the validation surface.

## `scripts/install_repo_git_config.py`

Install the repo-local Git configuration expected by this repository,
including hooks, commit template, and sanctioned aliases.

## `scripts/run_with_repo_python.sh`

Resolve the repository Python interpreter deterministically and execute Python
arguments through it.

## `scripts/check_commit_messages.py`

Validate commit headers for semantic-release compatibility.

This script is used by the GitHub commit-message workflow and enforces the
repository's conventional-commit contract.

## `scripts/clean_repo.py`

Clean ignored repository artifacts using Git as the source of truth rather than
custom filesystem heuristics.

## `scripts/ri_fix.py`

Repository helper for local maintenance tasks used during development.

Review the script directly before use if you need exact behavior for a given
operation.
