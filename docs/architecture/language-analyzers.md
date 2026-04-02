# Language Analyzers

The current repository now has two active analyzers:

- Python for the existing AST-driven index surface
- C for the first non-Python proof required by `ADR-004`, installed through
  the optional `repoindex[c]` extra

## Current Analyzer Responsibilities

The Python analysis path currently performs:

- module, class, and function extraction
- import collection
- static call-record extraction
- callable-reference extraction
- docstring validation integration

Today these responsibilities are concentrated in:

- `src/repoindex/parser_ast.py`
- `src/repoindex/analyzers/python.py`
- `src/repoindex/analyzers/c.py`
- `src/repoindex/indexer.py` for analyzer routing only

## Current Scope Boundary

`scanner.iter_project_files()` now derives discovery globs from the active
analyzer set instead of relying on a hard-coded core tuple.

Each analyzer declares deterministic `discovery_globs`, and scanner discovery
uses those globs for both:

- Git-backed tracked-file discovery
- filesystem fallback outside Git repositories

Phase 19 adds a second scanner path for canonical coverage auditing:

- `src/`
- `tests/`
- `scripts/`

Tracked files under those directories are inspected for coverage even if no
active analyzer claims them yet.

The retrieval-capability migration does not currently widen analyzer
responsibilities.

Built-in analyzers still own:

- language-specific parsing
- normalized artifact extraction
- durable symbol identity for indexed artifacts

They do not yet need to implement `RetrievalProducer`. Retrieval-facing
capability metadata currently lives in shared query producer descriptors
instead.

## Accepted Migration Direction

`ADR-004` expands this boundary by accepting:

- multiple analyzers in one indexing run
- mixed-language repositories as a first-class target
- a future proof analyzer beyond Python, with C named as the preferred first
  validation target

## Phase-6 Baseline

Phase 6 now extracts the current Python analysis path into
`src/repoindex/analyzers/python.py`.

That module owns:

- Python parsing through `parser_ast.parse_file()`
- normalization into `AnalysisResult`
- Python file acceptance through the `LanguageAnalyzer` contract

## Phase-8 Registration Rules

Phase 8 moves analyzer registration into `src/repoindex/registry.py`.

- analyzers are instantiated from a code-level registry
- registry order defines deterministic first-match routing order
- an empty analyzer registry raises `ValueError`
- optional analyzers may be omitted when their declared extras are not
  installed

## Phase-9 Second Analyzer Proof

Phase 9 adds `src/repoindex/analyzers/c.py` and registers it after Python.

- Python keeps the full AST-driven extraction path
- C currently extracts module identity, include dependencies, and top-level
  function definitions
- mixed-language repositories are now indexed in one deterministic run

The C analyzer is intentionally narrow. It exists to prove the abstraction and
file-routing model before any deeper C-specific call analysis work.

## Current C Parser Boundary

The current C analyzer is now backed by `tree-sitter-c`.

That gives the branch:

- parse-tree-based function extraction
- parse-tree-based include extraction
- AST-based call extraction for direct and attribute calls
- a safer foundation for future include-graph and symbol-parity work

The normalized artifact model and backend contracts remain unchanged. Only the
language-specific C parsing strategy has been upgraded.

## Dependency Boundary

The packaging surface now distinguishes core `repoindex` dependencies from
analyzer-specific dependencies.

- core install keeps Python analysis available
- the C analyzer loads only when `tree-sitter` and `tree-sitter-c` are present
- the supported install form for C-family indexing is `repoindex[c]`
- third-party analyzers must declare their own discovery globs so indexing can
  see their files without core changes

When those optional dependencies are absent, registry activation skips the C
analyzer deterministically and indexing a `*.c` or `*.h` path fails with an
explicit installation hint instead of an import-time crash.
