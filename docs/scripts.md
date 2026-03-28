# Scripts

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
