# Contributing

## Source of truth

The repository filesystem is the source of truth. Do not assume structures,
modules, or workflows that are not present in the repo.

## Validation

Run the standard local validation loop before concluding a change:

```bash
git check
black --check .
ruff check .
mypy .
pytest
```

Use the repository-local `.venv` for all Python-facing tools.

## Bootstrap

A fresh clone can be initialized with:

```bash
python3 scripts/bootstrap_dev_environment.py
```

That bootstrap flow creates `.venv`, installs development and documentation
dependencies, and installs repo-local Git configuration.

## Context exploration

Before broad patching work:

```bash
repoindex context-for "<query>" --json
```

Use `rg` first when you need to verify candidate symbols or files.

## Architectural work

ADR-driven architecture changes should be linked to the corresponding
documentation under `docs/adr/`.

The accepted migration direction for pluggable backends and analyzers is
documented in `ADR-004`, but that work is expected to land on its own
dedicated branch.
