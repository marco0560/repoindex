# Release Checklist

1. Ensure the working tree is clean.
2. Run `git check`.
3. Run `black --check .`.
4. Run `ruff check .`.
5. Run `mypy .`.
6. Run `pytest`.
7. Run `git release-audit`.
8. Push the releasable commits with `git rel`.
9. Confirm the GitHub release workflow creates the expected tag and GitHub release.
