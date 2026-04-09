# Getting Started

## Bootstrap this repository

Create the local development environment and install the repo-local Git
configuration:

```bash
python3 scripts/bootstrap_dev_environment.py
```

The bootstrap script installs the core package, the extracted first-party
analyzer/backend packages, and the local embedding dependencies. It also
provisions the local model artifact used by the real embedding backend, so
`repoindex index` can build persisted embeddings without ad hoc first-run
downloads inside this repository.

The repository-local first-party package set is owned by:

```bash
python scripts/install_first_party_packages.py
```

## Install into another repository

Install `repoindex` into the virtual environment of the repository you want to
analyze.

Example:

```bash
source .venv/bin/activate
pip install -e ../repoindex[semantic]
pip install -e ../repoindex/packages/repoindex-analyzer-python
pip install -e ../repoindex/packages/repoindex-analyzer-json
pip install -e ../repoindex/packages/repoindex-analyzer-c
pip install -e ../repoindex/packages/repoindex-analyzer-bash
pip install -e ../repoindex/packages/repoindex-backend-sqlite
```

This keeps the `repoindex` CLI available in the target repository while using
the live source tree from this repository.

The current source-tree install keeps the embedding stack in the core package
while the extracted first-party analyzers and backend are installed from
`packages/`.
The accepted published bundle name is `repoindex[bundle-official]`. Inside the
current source tree, the extracted first-party packages are still installed
explicitly from `packages/`, and the canonical local package set is the one
installed by `scripts/install_first_party_packages.py`.

Use `repoindex plugins` after installation if you want to verify whether a
capability came from the core package, an official extracted package, or a
third-party plugin.

On first indexing run, `repoindex` provisions the configured local model
artifact automatically if it is missing. If automatic provisioning cannot
complete, the CLI fails with a concise remediation message.

You can still prefetch the model explicitly:

```bash
source .venv/bin/activate
python ../repoindex/scripts/provision_embedding_model.py
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

Inspect bounded graph traversal and optional DOT export:

```bash
repoindex calls build_parser --tree
repoindex calls build_parser --tree --dot
repoindex refs _retrieve_script_candidates --incoming --tree
repoindex refs _retrieve_script_candidates --incoming --tree --dot
```

## Validation surface

The repository expects contributors to run:

```bash
source .venv/bin/activate
black --check src scripts tests
ruff check src scripts tests
mypy src scripts tests
pytest -q
```

Use the repository `.venv` for all Python-facing commands.
