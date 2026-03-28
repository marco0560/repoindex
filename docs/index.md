# repoindex

`repoindex` is a repository-local indexing and context retrieval tool for
agent-assisted development.

It builds a SQLite index inside the target repository and currently provides:

- exact symbol lookup
- docstring auditing
- deterministic local semantic embeddings
- deterministic context generation for natural-language queries

## Documentation scope

This documentation set is intentionally small for now. It covers:

- how to install and use the current tool locally
- how contributors should validate changes
- the small set of repository-owned helper scripts
- the active ADR trail

## Current architecture status

The current implementation is SQLite-backed and Python-analysis-first.

The accepted future architectural direction is documented in
[`ADR-004`](adr/ADR-004-pluggable-backends-migration-plan.md), but that
migration is not part of the current branch of work.
