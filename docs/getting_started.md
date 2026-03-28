# Getting Started

## Local development install

Install `repoindex` into the virtual environment of the repository you want to
analyze.

Example:

```bash
source .venv/bin/activate
pip install -e ../repoindex
```

This keeps the `repoindex` CLI available in the target repository while using
the live source tree from this repository.

## First commands

Build or refresh the repository-local index:

```bash
repoindex index
```

Inspect exact symbol data:

```bash
repoindex symbol build_parser
repoindex symbol build_parser --json
```

Inspect context retrieval:

```bash
repoindex context-for "schema migration rules"
repoindex context-for "missing numpy docstring" --json
```

## Current validation surface

The repository currently expects contributors to run:

```bash
git check
black --check .
ruff check .
mypy .
pytest
```

Use the repository `.venv` for all Python-facing commands.
