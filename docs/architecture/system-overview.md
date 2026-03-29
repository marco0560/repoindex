# System Overview

`repoindex` currently consists of four practical layers:

| Layer | Current responsibility |
| --- | --- |
| scanner | discover repository files for indexing |
| indexer | orchestrate analyzer routing, normalized artifacts, and backend persistence |
| query | resolve exact and semantic retrieval against the repository index |
| CLI | expose repository-local commands and output contracts |

The implementation is intentionally repository-local:

- the CLI operates relative to the current repository root
- index data lives under `.repoindex/`
- exact and semantic query paths read the same SQLite database

## Current Module Shape

The current branch centers on these modules:

- `src/repoindex/cli.py` for command parsing and output formatting
- `src/repoindex/scanner.py` for Git-backed file discovery with filesystem
  fallback
- `src/repoindex/registry.py` for backend selection and analyzer activation
- `src/repoindex/indexer.py` for incremental orchestration and SQLite backend
  persistence/query implementation
- `src/repoindex/analyzers/python.py` and `src/repoindex/analyzers/c.py` for
  language-specific analysis
- `src/repoindex/storage.py` for SQLite initialization and schema refresh
- `src/repoindex/query/exact.py` for exact lookup helpers
- `src/repoindex/query/context.py` and `src/repoindex/semantic/search.py` for
  context retrieval and embedding-backed ranking

## ADR-004 Boundary

`ADR-004` now defines the architecture that this branch implements:

- one active index backend per repository instance
- multiple language analyzers in one indexing run
- documentation and tests landing alongside architectural refactors

The remaining future work is no longer about introducing these boundaries. It
is about extending them without breaking the current contracts.
