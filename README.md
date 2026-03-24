# repoindex

`repoindex` is a repository-local indexing and context retrieval tool for
agent-assisted development.

It builds a SQLite index inside the target repository, supports exact symbol
lookup, docstring auditing, and deterministic context generation for natural
language queries.

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

## Commands

Build or refresh the repository-local index:

```bash
repoindex index
```

Audit indexed docstrings:

```bash
repoindex audit-docstrings
```

Query exact symbols:

```bash
repoindex symbol build_parser
```

Generate deterministic context for a natural-language query:

```bash
repoindex context-for "missing numpy docstring"
```

Emit structured JSON for agent workflows:

```bash
repoindex context-for "missing numpy docstring" --json
```

Emit a prompt-oriented view:

```bash
repoindex context-for "parse inventory validation flow" --prompt
```

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

Use the plain text mode when you want a compact human-readable summary:

```bash
repoindex context-for "missing numpy docstring"
```

Use JSON when another tool or agent workflow needs structured output:

```bash
repoindex context-for "missing numpy docstring" --json
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

- it is not a full semantic embedding system
- it does not prove behavior correctness on its own
- it does not replace reading the referenced files
- it does not authorize blind edits based only on retrieved snippets
- it is only as current as the indexed repository state

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
