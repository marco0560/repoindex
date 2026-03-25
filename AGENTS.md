# AGENTS.md

## Purpose

This document defines the rules, workflow, and constraints for AI-assisted
development in the `repoindex` project.

All agents (including ChatGPT) MUST follow these rules strictly.

---

## Core Principles

### 1. Source of Truth (SOT)

- The repository filesystem is the ONLY source of truth.
- Never assume files, modules, or structures that are not present.
- Never reconstruct code from memory.

If something is not visible → STOP.

If any required information is missing:

→ STOP
→ Ask for clarification

---

### 2. Deterministic Behavior

- No guessing
- No approximations
- No “best effort”

All outputs must be:

- reproducible
- verifiable
- minimal

---

### 3. Strict Patch Discipline

All code changes MUST be provided as:

- explicit file paths
- exact OLD / NEW blocks

No summaries. No partial edits.

---

### 4. Minimalism (LEAN)

- Prefer the smallest correct solution
- Avoid introducing abstractions prematurely
- Avoid “framework thinking”

---

## Development Workflow

### Standard Loop

1. Analyze request
2. Propose plan, ask all necessaary clarification questions
3. Wait for approval or changes
4. Execute plan
5. Run:

   ```bash
   git check
   ```

6. Verify:

   - `black .` passes
   - `ruff check .`passes
   - `mypy .` passes
   - tests pass
   - If any would fail → fix BEFORE concluding

7. Manually validate behavior if needed
8. Propose a **single commit block** that is:

   - 15 - 20 lines long
   - atomic
   - CI-compliant

### repoindex Workflow

Use `repoindex` as a repository-local developer tool.

Before broad code exploration or patching:

1. Verify candidate symbols with `rg <query>` before editing.
2. Run `repoindex context-for "<query>" --json` or `--prompt` as needed.
3. Inspect the referenced files before applying changes.

Use output modes as follows:

- plain `context-for`: compact human-readable context
- `context-for --json`: structured tool/agent workflows
- `context-for --prompt`: copy-ready agent preamble
- `context-for --explain`: retrieval diagnostics

`repoindex` narrows search and improves determinism. It does not replace
reading the actual source files before editing.

### Virtual Environment

This repository is operated from the local `.venv` environment.

All Python-facing tools and entry points MUST resolve from `.venv`, not from
the system installation or ambient `PATH`.

Use one of these forms consistently:

- `source .venv/bin/activate` before running project tools
- explicit `.venv/bin/<tool>` paths when activation is not appropriate

Assume all tool paths, Python interpreters, and console scripts are based on
`.venv`.

---

### Cleanup

Before critical operations:

```bash
git clean-repo
repoindex index
```

---

### Context Exploration

Use:

```bash
git ctx <query>
```

to inspect symbols and relationships.

---

## Coding Standards

### Python

- Type hints required
- No `Any` unless justified
- Prefer `Path` over string paths

---

### Docstrings

- Use **NumPy style**
- Required for all modules, classes, non trivial functions
- Must include:

  - Parameters
  - Returns

- Includes if appropriate

  - `Raises` when exceptions are possible
  - `Notes`
  - `Examples`

Docstrings must:

- match actual behavior (no drift)
- reflect current signature
- include `Raises` when exceptions are possible
- avoid redundancy
- be concise and precise

---

### Error Handling

- Avoid broad `except Exception`
- Catch only expected exceptions
- Fail fast

---

## Architecture Rules

### Separation of Concerns

| Layer      | Responsibility       |
|------------|----------------------|
| scanner    | filesystem → symbols |
| indexer    | symbols → database   |
| query      | database → results   |
| CLI        | user interface       |

Do not mix layers.

---

### Git is the Source of Truth for Cleanup

- Cleanup logic MUST rely on git
- Never implement custom filesystem heuristics

---

## Anti-Patterns (Forbidden)

- Blind filesystem scanning when git provides truth
- Re-implementing logic already present elsewhere
- Introducing caching without clear invalidation rules
- Silent failures

---

## Agent Roles

Agents may act as:

- Senior Reviewer
- Pair Programmer
- Refactoring Assistant

But MUST always:

- respect SOT
- avoid hallucination
- produce deterministic output

---

## When in Doubt

STOP and ask for clarification.

Never proceed with assumptions.

---

## Future Extensions

This file may evolve to include:

- audit workflows
- release discipline
- semantic indexing policies

---

END
