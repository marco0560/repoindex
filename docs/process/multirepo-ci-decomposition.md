# Multirepo CI Decomposition

## Purpose

This note records the CI contract each future repository should carry after the
Phase 3 split.

It is intentionally narrower than the current monorepo `CI` workflow. The goal
is to make the post-split repository jobs explicit before files move, so the
split does not invent CI behavior package by package.

## Source Of Truth

The executable source of truth for this decomposition is:

* `scripts/future_repo_ci.py`

The regression coverage for that contract lives in:

* `tests/test_future_repo_ci.py`

## Core Repository

Repository:

* `repoindex`

Purpose:

* contracts
* registry/discovery
* CLI orchestration
* shared indexing/query/storage layers
* cross-package integration validation

Install commands:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev,docs,semantic]"
```

Validation commands:

```bash
python -m pre_commit run --all-files
python -m black --check src scripts tests
python -m ruff check src scripts tests
python -m mypy src scripts tests
python -m pytest -q
```

Notes:

* The core repo keeps the installed-wheel integration test that verifies plugin
  discovery without sibling-source loading.
* The core repo no longer owns package-local metadata assertions that have
  moved under `packages/*/tests`.

## Package Repositories

Repositories:

* `repoindex-analyzer-python`
* `repoindex-analyzer-json`
* `repoindex-analyzer-c`
* `repoindex-analyzer-bash`
* `repoindex-backend-sqlite`

Install command:

```bash
python -m pip install -e ".[test]"
```

Validation commands:

```bash
python -m black --check src tests
python -m ruff check src tests
python -m mypy src tests
python -m pytest -q tests
```

Notes:

* Each package now has package-local tests under its own `tests/` directory.
* Package-local README verification snippets already point at those test paths.

## Bundle Repository

Repository:

* `repoindex-bundle-official`

Install command:

```bash
python -m pip install -e ".[test]"
```

Validation commands:

```bash
python -m black --check tests
python -m ruff check tests
python -m mypy tests
python -m pytest -q tests
```

Notes:

* The bundle repo is metadata-heavy and does not own a `src/` tree.
* The package-local test remains focused on dependency metadata integrity.
