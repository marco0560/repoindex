# Release Checklist

1. Ensure the working tree is clean.
2. Run `source .venv/bin/activate`.
3. Run `black --check src scripts tests`.
4. Run `ruff check src scripts tests`.
5. Run `mypy src scripts tests`.
6. Run `pytest -q`.
7. Run `git release-audit`.
8. Push the releasable commits with `git rel`.
9. Confirm the GitHub release workflow creates the expected tag and GitHub release.
