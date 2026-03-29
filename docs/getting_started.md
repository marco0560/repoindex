# Getting Started

## Bootstrap this repository

Create the local development environment and install the repo-local Git
configuration:

```bash
python3 scripts/bootstrap_dev_environment.py
```

The bootstrap script installs the `semantic` extra and provisions the local
embedding model artifact used by the real local embedding backend, so
`repoindex index` can build persisted embeddings without ad hoc first-run
downloads inside this repository.

## Install into another repository

Install `repoindex` into the virtual environment of the repository you want to
analyze.

Example:

```bash
source .venv/bin/activate
pip install -e ../repoindex[semantic]
```

This keeps the `repoindex` CLI available in the target repository while using
the live source tree from this repository.

If the semantic extra is not installed, indexing fails fast with an explicit
dependency error instead of silently degrading or downloading model artifacts
in the background.

If the semantic extra is installed but the local model artifact is missing,
run:

```bash
source .venv/bin/activate
python scripts/provision_embedding_model.py
```

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

## Validation surface

The repository expects contributors to run:

```bash
git check
black --check .
ruff check .
mypy .
pytest
```

Use the repository `.venv` for all Python-facing commands.
