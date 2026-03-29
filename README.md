# repoindex

[![CI](https://github.com/marco0560/repoindex/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/marco0560/repoindex/actions/workflows/ci.yml)
[![Docs](https://github.com/marco0560/repoindex/actions/workflows/docs.yml/badge.svg?branch=main)](https://marco0560.github.io/repoindex/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

`repoindex` is a repository-local indexing and context retrieval tool for
agent-assisted development.

It builds a SQLite index inside the target repository, supports exact symbol
lookup, docstring auditing, deterministic local semantic embeddings, and
deterministic context generation for natural-language queries.

The current branch now indexes mixed-language repositories through registered
language analyzers:

- Python via `PythonAnalyzer`
- C-family `*.c` and `*.h` files via `CAnalyzer` backed by `tree-sitter-c`

Storage and query persistence remain SQLite-backed through the active backend
registry.

## Repository Documentation

The repository-local operational and contributor documentation is organized
under `docs/`.

Start with:

- `docs/getting_started.md`
- `docs/CONTRIBUTING.md`
- `docs/architecture/index.md`
- `docs/plugins/index.md`
- `docs/release/checklist.md`
- `docs/release/process.md`
- `docs/process/branching.md`
- `docs/process/decisions.md`
- `docs/adr/index.md`

## Install for Local Development

Install `repoindex` into the virtual environment of the repository you want to
analyze.

Example: from a target repository such as Fontshow:

```bash
source .venv/bin/activate
pip install -e ../repoindex
```

The editable install keeps the `repoindex` CLI available in the target
repository's virtual environment while still using the live source tree from
this repository.

Install optional analyzer dependencies only when needed. For C-family support:

```bash
source .venv/bin/activate
pip install -e ../repoindex[c]
```

## Architecture Status

The current architecture after completed `ADR-004` migration work is:

- one active backend per repository instance, selected through
  `repoindex.registry`
- SQLite as the only current concrete backend
- multiple language analyzers in one indexing run
- deterministic mixed-language indexing for tracked `*.py`, `*.c`, and `*.h`
  files
- query-time retrieval planning with deterministic intent families for
  behavior, test, configuration, API-surface, and architecture/navigation
  queries

The detailed architecture and migration record live under:

- `docs/architecture/index.md`
- `docs/adr/ADR-004-pluggable-backends-migration-plan.md`

## Commands

Build or refresh the repository-local index:

```bash
repoindex index
```

Indexing also precomputes local deterministic embeddings for indexed symbols.
Unchanged files are reused by default.

Force a full rebuild:

```bash
repoindex index --full
```

Show incremental reuse decisions:

```bash
repoindex index --explain
```

Inspect canonical-directory analyzer coverage without building the index:

```bash
repoindex coverage
repoindex coverage --json
```

Require full canonical coverage before indexing:

```bash
repoindex index --require-full-coverage
```

Audit indexed docstrings:

```bash
repoindex audit-docstrings
repoindex audit-docstrings --json
repoindex audit-docstrings --prefix src/repoindex/query
```

For Python callables, `audit-docstrings` applies Python-aware result-section
rules:

- regular functions should document `Returns` and not `Yields`
- generator and async-generator functions should document `Yields`
- generators may also document `Returns` only when they explicitly use
  `return <value>` to produce a terminal `StopIteration.value`

Query exact symbols:

```bash
repoindex symbol build_parser
repoindex symbol build_parser --json
repoindex symbol build_parser --prefix src/repoindex
```

Inspect embedding-only matches and backend metadata:

```bash
repoindex embeddings "schema migration rules"
repoindex embeddings "schema migration rules" --json
repoindex embeddings "schema migration rules" --prefix src/repoindex/query
```

Inspect static call edges:

```bash
repoindex calls context_for
repoindex calls context_for --json
repoindex calls imported_helper --module pkg.b --incoming
repoindex calls imported_helper --module pkg.b --incoming --prefix src/repoindex/query
```

Inspect callable-object references such as registry bindings:

```bash
repoindex refs _retrieve_script_candidates --module repoindex.query.context --incoming
repoindex refs _retrieve_script_candidates --incoming --json
repoindex refs _retrieve_script_candidates --incoming --prefix src/repoindex/query
```

Generate deterministic context for a natural-language query:

```bash
repoindex context-for "missing numpy docstring"
repoindex context-for "missing numpy docstring" --prefix src/repoindex
```

Embedding-assisted retrieval works best for natural-language queries such as:

```bash
repoindex context-for "schema migration rules"
```

Emit structured JSON for agent workflows:

```bash
repoindex context-for "missing numpy docstring" --json
repoindex context-for "missing numpy docstring" --json --prefix src/repoindex/query
```

Emit a prompt-oriented view:

```bash
repoindex context-for "parse inventory validation flow" --prompt
```

## Using `--prefix`

Use `--prefix <path>` to scope supported read/query subcommands to one
repo-root-relative directory or file.

Examples:

```bash
repoindex symbol build_parser --prefix src/repoindex
repoindex embeddings "schema migration rules" --prefix src/repoindex/query
repoindex calls imported_helper --module pkg.b --incoming --prefix src/repoindex/query
repoindex refs _retrieve_script_candidates --incoming --prefix src/repoindex/query
repoindex audit-docstrings --prefix src/repoindex/query
repoindex context-for "missing numpy docstring" --json --prefix src/repoindex/query
```

Semantics:

- `symbol --prefix P NAME`: only symbols whose defining file is under `P`
- `embeddings --prefix P QUERY`: only matched symbols whose file is under `P`
- `context-for --prefix P QUERY`: retrieval, expansion, issues, and references
  are restricted to files under `P`
- `calls --prefix P NAME`: only call edges whose caller file is under `P`
- `refs --prefix P NAME`: only callable-object references whose owner file is
  under `P`
- `audit-docstrings --prefix P`: only issues for symbols defined under `P`

`--prefix` must be relative to the repository root. It may point to either a
directory or a single file.

## Using `--json`

Use `--json` on the exact/query subcommands when another tool or agent needs a
machine-readable result instead of human-oriented text.

Supported subcommands:

- `symbol`
- `embeddings`
- `calls`
- `refs`
- `audit-docstrings`
- `context-for`

Examples:

```bash
repoindex symbol build_parser --json
repoindex embeddings "schema migration rules" --json --prefix src/repoindex/query
repoindex calls imported_helper --module pkg.b --incoming --json
repoindex refs _retrieve_script_candidates --incoming --json --prefix src/repoindex/query
repoindex audit-docstrings --json --prefix src/repoindex/query
repoindex context-for "missing numpy docstring" --json
```

For `symbol`, `embeddings`, `calls`, `refs`, and `audit-docstrings`, the JSON
contract uses a lightweight shared envelope:

```json
{
  "schema_version": "1.0",
  "command": "symbol",
  "status": "ok",
  "query": {
    "name": "build_parser",
    "prefix": "src/repoindex"
  },
  "results": []
}
```

Status values:

- `ok`: one or more results were found
- `no_matches`: the filtered query returned no results
- `not_indexed`: the command requires indexed embedding data that is not present

`context-for --json` keeps its existing richer retrieval schema. It is not part
of the lightweight query-envelope contract above.

## Using `--prompt`

Use `repoindex context-for "<query>" --prompt` when you want a compact,
copy-ready prompt for an agent session.

Recommended use cases:

- starting a focused bug-fix task
- preparing a docstring audit pass
- analyzing an external repository before patching
- resuming work on a specific subsystem after context switching

Recommended workflow:

1. Verify likely symbols or files with `rg`.
2. Run `repoindex index`.
3. Run `repoindex context-for "<query>" --prompt`.
4. Read the returned files and symbols before editing.

The prompt view is optimized for fast operator handoff. It is not a substitute
for reading the referenced files.

## Choosing an Output Mode

Use the plain text mode when you want a compact human-readable summary across
the symbol, semantic, and embedding channels:

```bash
repoindex context-for "missing numpy docstring"
```

Use JSON when another tool or agent workflow needs structured output:

```bash
repoindex context-for "missing numpy docstring" --json
repoindex symbol build_parser --json
```

Use prompt mode when you want a copy-ready task preamble:

```bash
repoindex context-for "parse inventory validation flow" --prompt
```

Use explain mode when you need retrieval diagnostics:

```bash
repoindex context-for "missing numpy docstring" --explain
```

Practical rule:

- plain text: human inspection
- `--json`: automation and downstream tooling
- `--prompt`: agent handoff
- `--explain`: debugging retrieval behavior

The `embeddings` command is a debugging surface for the embedding channel only.
Use it when you want backend metadata and raw embedding-ranked matches without
the normal multi-channel merge used by `context-for`.

## Query Examples

Natural-language queries:

```bash
repoindex context-for "missing numpy docstring"
repoindex context-for "parse inventory validation flow"
repoindex context-for "where is schema validation performed"
repoindex context-for "how does release tagging work"
repoindex context-for "semantic merge ordering"
```

Exact symbol lookup:

```bash
repoindex symbol build_parser
repoindex symbol context_for
repoindex symbol validate_docstring
```

Static call-edge inspection:

```bash
repoindex calls context_for
repoindex calls imported_helper --module pkg.b --incoming
```

Callable-reference inspection:

```bash
repoindex refs _retrieve_script_candidates --module repoindex.query.context --incoming
```

The most useful queries are usually:

- behavior-oriented
- scoped to one subsystem
- phrased in terms of the problem you are solving

Prefer specific queries over broad ones such as `"project structure"` or
`"everything about indexing"`.

## Reindexing and Freshness

Rerun `repoindex index` when the repository state has changed enough that the
existing `.repoindex/` snapshot may no longer reflect the current code.

Typical cases:

- after significant code changes
- after switching branches
- after rebases, pulls, or merges
- before a larger audit session
- before querying a repository that has not been indexed yet

The index is repository-local and intentionally conservative. Rebuilding it is
cheap compared with working from stale symbol or docstring data.

Practical rule:

```bash
repoindex index
```

Run it again whenever you would not trust an earlier search result to describe
the current working tree.

## Limits and Expectations

`repoindex` is a retrieval and inspection tool. It narrows search and improves
determinism, but it does not replace direct source inspection.

Important limits:

- it includes a deterministic in-repo embedding backend rather than a full
  external-model semantic stack
- stored embeddings carry explicit backend and version metadata so the backend
  can be replaced later without changing the retrieval interface
- it does not prove behavior correctness on its own
- it does not replace reading the referenced files
- it does not authorize blind edits based only on retrieved snippets
- it is only as current as the indexed repository state
- embedding recall is intentionally lightweight and local-first in the current
  implementation
- `repoindex calls` only covers direct static call sites
- `repoindex refs` should be used for callable-object references such as
  registry values, assignment values, and returned function objects
- `context-for` uses stored call and callable-reference data to pull in
  related cross-module symbols around top function and method matches

Recommended use:

- use `repoindex` to find likely files, symbols, and related issues
- use `rg` to verify concrete symbol existence
- read the actual files before patching
- rerun tests and validation after changes

## Recommended Workflow in an External Repository

Run `repoindex` from the target repository, not from the `repoindex` source
tree.

Example workflow:

1. Activate the target repository virtual environment.
2. Run `repoindex index`.
3. Verify candidate symbols with `rg <query>` before patching.
4. Run `repoindex context-for "<query>" --json`.
5. Inspect the actual files and symbols returned.
6. Apply changes only after verification.
7. Rebuild the index after material source changes.

This keeps the `.repoindex/` cache local to the analyzed repository and avoids
cross-repo state drift.

## Suggested Shell Aliases

```bash
alias ri='repoindex'
alias ri-index='repoindex index'
alias ri-audit='repoindex audit-docstrings'
alias ri-ctx='repoindex context-for'
alias ri-docs='repoindex context-for "missing numpy docstring" --json'
```

## Optional Helper Script

A thin wrapper script in the target repository can make the workflow more
repeatable:

```bash
#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
repoindex "$@"
```

Example target-repo setup:

```bash
mkdir -p scripts
cat > scripts/ri.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
repoindex "$@"
EOF
chmod +x scripts/ri.sh
```

Then run:

```bash
./scripts/ri.sh index
./scripts/ri.sh audit-docstrings
./scripts/ri.sh context-for "missing numpy docstring" --json
```

## Integration Guidance

Use `repoindex` as a developer tool.

Recommended:

- install it editable into the target repository virtual environment
- keep the index local to the target repository
- verify symbol existence with `rg` before editing

Not recommended:

- global installation for day-to-day work
- treating `repoindex` as a runtime dependency of the target project
- relying on ad-hoc `PYTHONPATH` launch patterns for normal usage

## AGENTS.md Snippet for Target Repositories

If you want a target repository to standardize `repoindex` usage, this snippet
can be copied into its `AGENTS.md`:

```text
### repoindex Workflow

Use `repoindex` as a repository-local developer tool.

Before broad code exploration or patching:

1. Activate the repository virtual environment.
2. Run `repoindex index`.
3. Verify candidate symbols with `rg <query>` before editing.
4. Run `repoindex context-for "<query>" --json` or `--prompt` as needed.
5. Inspect the referenced files before applying changes.

Use output modes as follows:

- plain `context-for`: compact human-readable context
- `context-for --json`: structured tool/agent workflows
- `context-for --prompt`: copy-ready agent preamble
- `context-for --explain`: retrieval diagnostics

`repoindex` narrows search and improves determinism. It does not replace
reading the actual source files before editing.
```
