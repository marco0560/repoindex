# Codira Rebrand Migration Plan

## Version

Document version: `0.1.2`

Status: accepted working plan, not yet executed.

This document supersedes the root-level draft `migration-plan.md` for the
`repoindex` to `codira` rebrand.

## Change Log

- `0.1.0`: Record the corrected target name, the accepted `v1.0.0` version
  reset, the `pre-rebrand-snapshot` tag, the complete package/API rename scope,
  the repository validation contract, the tool-usability prerequisite, and the
  CLI subcommand-shortening requirement.
- `0.1.1`: Complete the Phase 0 local and split-repository tool smoke checks,
  add split-package-root support to the first-party install helper, and record
  the remaining `.typed` coverage classification.
- `0.1.2`: Complete the Phase 1 local state audit, verify
  `pre-rebrand-snapshot`, remove cleanup-tool-managed artifacts, and record
  PyPI namespace status for the old and new package names.

## Purpose

This ledger records the executable migration from the current `repoindex`
project identity to the new `codira` identity.

It is intentionally checklist-based. During implementation, each completed
step must be checked off in this document so the migration state remains visible
and auditable.

## Fixed Decisions

- [ ] Use `codira` as the new project name.
- [ ] Treat the earlier `codera` spelling as a typo.
- [ ] Use `pre-rebrand-snapshot` as the historical snapshot tag name.
- [ ] Start the public `codira` release line at `v1.0.0` intentionally, even
  though the old `repoindex` line reached `v2.0.0`.
- [ ] Publish the core distribution as `codira`.
- [ ] Publish first-party distributions under the `codira-*` namespace.
- [ ] Rename public APIs from `repoindex*` to `codira*`; do not keep the old
  public names as supported compatibility surfaces for the new project.
- [ ] Keep the old `repoindex` GitHub repository public and archived after
  issue triage, instead of making it private.
- [ ] Create a new public GitHub repository named `codira` with fresh history.

## Target Package Set

The intended published package set is:

- [ ] `codira`
- [ ] `codira-analyzer-python`
- [ ] `codira-analyzer-json`
- [ ] `codira-analyzer-c`
- [ ] `codira-analyzer-bash`
- [ ] `codira-backend-sqlite`
- [ ] `codira-bundle-official`

The old package set must not appear in active package metadata after the rename:

- [ ] `repoindex`
- [ ] `repoindex-analyzer-python`
- [ ] `repoindex-analyzer-json`
- [ ] `repoindex-analyzer-c`
- [ ] `repoindex-analyzer-bash`
- [ ] `repoindex-backend-sqlite`
- [ ] `repoindex-bundle-official`

## Target Public API Surface

The rebrand is a public API rename, not only a repository rename.

Required public surface changes:

- [ ] CLI executable: `repoindex` -> `codira`.
- [ ] Python import package: `repoindex` -> `codira`.
- [ ] First-party analyzer import packages:
  - [ ] `repoindex_analyzer_python` -> `codira_analyzer_python`
  - [ ] `repoindex_analyzer_json` -> `codira_analyzer_json`
  - [ ] `repoindex_analyzer_c` -> `codira_analyzer_c`
  - [ ] `repoindex_analyzer_bash` -> `codira_analyzer_bash`
- [ ] First-party backend import package:
  - [ ] `repoindex_backend_sqlite` -> `codira_backend_sqlite`
- [ ] Example plugin import packages:
  - [ ] `repoindex_demo_analyzer` -> `codira_demo_analyzer`
  - [ ] `repoindex_demo_backend` -> `codira_demo_backend`
- [ ] Plugin entry-point groups:
  - [ ] `repoindex.analyzers` -> `codira.analyzers`
  - [ ] `repoindex.backends` -> `codira.backends`
- [ ] Repository-local state directory: `.repoindex` -> `.codira`.
- [ ] Generated version file path: `src/repoindex/_version.py` ->
  `src/codira/_version.py`.
- [ ] Package data key: `repoindex = ["py.typed"]` ->
  `codira = ["py.typed"]`.
- [ ] Documentation, examples, badges, scripts, release notes, and developer
  prompts use `codira` unless they intentionally describe archived history.

Intentional historical references to `repoindex` are allowed only when they
are clearly marked as historical.

## CLI Subcommand Rename Contract

The rebrand includes shortening subcommands while keeping them mnemonic.

Accepted command names:

- [ ] `index` remains `index`.
- [ ] `coverage` becomes `cov`.
- [ ] `symbol` becomes `sym`.
- [ ] `embeddings` becomes `emb`.
- [ ] `calls` remains `calls`.
- [ ] `refs` remains `refs`.
- [ ] `audit-docstrings` becomes `audit`.
- [ ] `context-for` becomes `ctx`.
- [ ] `plugins` remains `plugins`.
- [ ] `help` remains `help`.

Required CLI behavior:

- [ ] `codira ctx` is the documented replacement for `repoindex context-for`.
- [ ] `codira audit` is the documented replacement for
  `repoindex audit-docstrings`.
- [ ] `codira cov` is the documented replacement for `repoindex coverage`.
- [ ] `codira sym` is the documented replacement for `repoindex symbol`.
- [ ] `codira emb` is the documented replacement for `repoindex embeddings`.
- [ ] Help text, examples, tests, and docs use only the new command names.
- [ ] No old subcommand aliases are retained unless a later decision explicitly
  adds a temporary compatibility phase.

## Phase 0 - Restore Tool Usability Before Rebranding

Goal:
`repoindex` must be usable as a local developer tool before the rebrand starts.
It must work both on this repository and on another repository.

Current observed blocker:

- [x] `source .venv/bin/activate && repoindex index` previously failed in this
  checkout with `ValueError: No language analyzers are registered for
  repoindex`.

Tasks:

- [x] Confirm the active `.venv` installation state.
- [x] Confirm whether first-party analyzer and backend distributions are
  installed in `.venv`.
- [x] Fix the local developer bootstrap or installation flow so the active
  `.venv` can discover the first-party analyzer and backend entry points.
- [x] Ensure `repoindex plugins --json` reports the expected first-party
  analyzers and backend from installed distributions.
- [x] Ensure `repoindex coverage --json` works from this repository root.
  It currently reports incomplete coverage for `src/repoindex/py.typed`.
- [x] Ensure `repoindex index --full --json` works from this repository root.
- [x] Ensure `repoindex ctx "rename package metadata" --json` works from this
  repository root after the subcommand-shortening implementation, or
  `repoindex context-for "rename package metadata" --json` works before that
  implementation.
- [x] Run the same minimum tool-smoke sequence from one external repository:
  - [x] `repoindex plugins --json`
  - [x] `repoindex coverage --json`
  - [x] `repoindex index --full --json`
  - [x] one context retrieval query
- [x] Add or update tests that would have caught missing analyzer discovery in
  the repository-local developer workflow.

Exit criteria:

- [x] `repoindex` can index and query this repository from the active `.venv`.
- [x] `repoindex` can index and query at least one external repository from the
  active `.venv`.
- [x] The fix is validated by the current repository contract.

Phase 0 implementation note:

- [x] The active `.venv` now points first-party editable installs at
  `../repoindex-split-repos/`.
- [x] `scripts/install_first_party_packages.py` supports `--package-root` so
  maintainers can intentionally target exported split repositories.
- [x] `tests/test_bootstrap_scripts.py` verifies the split-package-root install
  command plan.
- [ ] Decide whether `py.typed` files should be ignored by coverage or covered
  by a metadata analyzer before requiring full coverage.

## Phase 1 - Freeze And Audit The Starting State

Goal:
Record the last intentional `repoindex` state before modifying identity.

Tasks:

- [x] Run `git status --short` and account for every untracked or modified
  file.
- [x] Create or verify the `pre-rebrand-snapshot` tag.
- [x] Record the current commit SHA.
- [x] Record the `pre-rebrand-snapshot` tag SHA.
- [x] Record the old PyPI project cleanup state for all seven old package
  names.
- [x] Record the final seven new PyPI package names.
- [x] Confirm target names are available or intentionally reserved where
  package indexes are involved.
- [x] Confirm no pending release artifacts remain in:
  - [x] `dist/`
  - [x] `build/`
  - [x] `src/repoindex.egg-info/`
  - [x] `packages/*/dist/`
  - [x] `packages/*/build/`
  - [x] `packages/*/src/*.egg-info/`
  - [x] `.artifacts/`
  - [x] `.repoindex/`
  - [x] `src/repoindex/_version.py`
- [x] Run repository cleanup only through repository-approved tooling.

Exit criteria:

- [x] The starting state can be reconstructed from local Git and this ledger.
- [x] There are no stale local artifacts that can contaminate the rename.

Phase 1 audit record:

- [x] Current commit SHA after Phase 0: `8a9d4d382e5128022493999c8bb0e65dd5ab6284`.
- [x] `pre-rebrand-snapshot` resolves to
  `eb3d2a17c6c10f68b4379d7a5307883c2b955fcb`.
- [x] `git status --short` was clean before the Phase 1 ledger update.
- [x] `git clean-repo` removed ignored build, cache, and package metadata
  artifacts.
- [x] `source .venv/bin/activate && repoindex index --full --json` passed
  after cleanup with 93 indexed files and zero failures.
- [x] Protected ignored runtime/generated state remains by repository policy:
  - [x] `.repoindex/`
  - [x] `src/repoindex/_version.py`
- [x] PyPI JSON endpoint status for target names on 2026-04-11:
  - [x] `codira`: 404
  - [x] `codira-analyzer-python`: 404
  - [x] `codira-analyzer-json`: 404
  - [x] `codira-analyzer-c`: 404
  - [x] `codira-analyzer-bash`: 404
  - [x] `codira-backend-sqlite`: 404
  - [x] `codira-bundle-official`: 404
- [x] PyPI JSON endpoint status for old names on 2026-04-11:
  - [x] `repoindex`: 200, occupied by package `repoindex` version `0.15.2`
    with summary `A collection-aware metadata index for git repositories`.
  - [x] `repoindex-analyzer-python`: 404
  - [x] `repoindex-analyzer-json`: 404
  - [x] `repoindex-analyzer-c`: 404
  - [x] `repoindex-analyzer-bash`: 404
  - [x] `repoindex-backend-sqlite`: 404
  - [x] `repoindex-bundle-official`: 404

## Phase 2 - Triage GitHub Issues

Goal:
Preserve only useful active work in the new `codira` issue tracker.

Tasks:

- [ ] Keep the old `repoindex` repository public while issue triage is in
  progress.
- [ ] Classify each current `repoindex` issue as:
  - [ ] still relevant to `codira`
  - [ ] historical only
  - [ ] obsolete
- [ ] Pre-create matching labels and milestones in `codira` where preserving
  them matters.
- [ ] Transfer only still-relevant open issues after the new `codira`
  repository exists.
- [ ] Leave closed, obsolete, and historical issues in the archived
  `repoindex` repository.

Exit criteria:

- [ ] The new `codira` issue tracker contains only intentional active work.
- [ ] The old `repoindex` issue tracker remains available for history.

## Phase 3 - Create The New Public GitHub Repository

Goal:
Create a clean target remote without disturbing the old repository location.

Tasks:

- [ ] Create a new public GitHub repository named `codira`.
- [ ] Do not rename the old `repoindex` repository in place.
- [ ] Do not transfer the old `repoindex` repository.
- [ ] Do not create a new repository at the old `repoindex` location after any
  rename or transfer operation.
- [ ] Configure the new repository with the expected default branch, branch
  protection, Actions settings, and trusted publishing settings if used.

Exit criteria:

- [ ] Old repository: `repoindex`, public, unchanged.
- [ ] New repository: `codira`, public, ready to receive fresh history.

## Phase 4 - Apply The Local Rebrand

Goal:
Rename the project in a local working copy while keeping the change minimal and
reviewable.

Tasks:

- [ ] Work in a copy or branch dedicated to the rebrand.
- [ ] Rename `src/repoindex/` to `src/codira/`.
- [ ] Rename package directories under `packages/`:
  - [ ] `packages/repoindex-analyzer-python/` ->
    `packages/codira-analyzer-python/`
  - [ ] `packages/repoindex-analyzer-json/` ->
    `packages/codira-analyzer-json/`
  - [ ] `packages/repoindex-analyzer-c/` ->
    `packages/codira-analyzer-c/`
  - [ ] `packages/repoindex-analyzer-bash/` ->
    `packages/codira-analyzer-bash/`
  - [ ] `packages/repoindex-backend-sqlite/` ->
    `packages/codira-backend-sqlite/`
  - [ ] `packages/repoindex-bundle-official/` ->
    `packages/codira-bundle-official/`
- [ ] Rename first-party package source roots under each package.
- [ ] Rename example plugin directories and source roots.
- [ ] Update root `pyproject.toml`.
- [ ] Update every package `pyproject.toml`.
- [ ] Update package dependencies and pins from `repoindex*` to `codira*`.
- [ ] Update all imports from `repoindex` to `codira`.
- [ ] Update all imports from `repoindex_*` first-party packages to
  `codira_*`.
- [ ] Update plugin discovery entry-point groups to `codira.analyzers` and
  `codira.backends`.
- [ ] Update registry/discovery code and error messages.
- [ ] Update the local state directory from `.repoindex` to `.codira`.
- [ ] Update scripts that own package inventories, release plans, split
  manifests, bootstrap, cleanup, and Git aliases.
- [ ] Update tests to assert the new package names, imports, entry points, CLI
  command names, cache directory, and error messages.
- [ ] Update docs, README, MkDocs config, badges, examples, release docs,
  architecture docs, ADR references, and developer prompts.
- [ ] Keep one explicit historical note in the new README:
  `This project was initially developed under the working name repoindex and
  was renamed to codira before the codira public release.`

Exit criteria:

- [ ] No active code, metadata, test, script, or documentation reference still
  uses `repoindex` except approved historical notes.
- [ ] Public APIs use `codira*`.

## Phase 5 - Apply CLI Subcommand Shortening

Goal:
Ship the new project identity with the shorter mnemonic command set.

Tasks:

- [ ] Update CLI parser command names.
- [ ] Update dispatch logic for the new command names.
- [ ] Update CLI usage examples.
- [ ] Update README command walkthroughs.
- [ ] Update AGENTS-style workflow snippets and developer prompts.
- [ ] Update tests for command parsing and CLI behavior.
- [ ] Update shell aliases and helper scripts from old commands to new
  commands.
- [ ] Confirm `codira --help` lists the new command set.
- [ ] Confirm old command names are absent unless explicitly approved later.

Exit criteria:

- [ ] `codira ctx`, `codira audit`, `codira cov`, `codira sym`, and
  `codira emb` work.
- [ ] The documented CLI surface contains only the accepted new subcommand
  names.

## Phase 6 - Drift Audit

Goal:
Find and classify every stale old-name reference before release.

Tasks:

- [ ] Run `rg -n "repoindex|repoindex-|repoindex_|\\.repoindex"`.
- [ ] Run `rg -n "context-for|audit-docstrings|coverage|symbol|embeddings"`
  and classify remaining old subcommand references.
- [ ] Inspect every remaining hit manually.
- [ ] Convert active references to `codira`.
- [ ] Mark intentional historical references with local context explaining why
  they remain.
- [ ] Verify package metadata names are exactly the accepted target names.
- [ ] Verify dependency metadata points only to `codira` packages.
- [ ] Verify entry-point groups are only `codira.analyzers` and
  `codira.backends`.

Exit criteria:

- [ ] Stale-reference search has no unexplained hits.
- [ ] Intentional historical references are few, explicit, and non-operational.

## Phase 7 - Local Validation

Goal:
Validate the renamed tree through the current repository contract and release
rehearsals.

Required repository checks:

```bash
source .venv/bin/activate
black --check src scripts tests
ruff check src scripts tests
mypy src scripts tests
pytest -q
```

Additional rename-specific checks:

- [ ] Extend the required checks to include `packages` and `examples` where
  rename-sensitive code lives.
- [ ] Build every distribution.
- [ ] Run artifact validation on every generated distribution.
- [ ] Install the core package locally in a fresh environment.
- [ ] Install the bundle package locally in a fresh environment.
- [ ] Verify `codira --help`.
- [ ] Verify `codira -V`.
- [ ] Verify `codira plugins --json`.
- [ ] Verify `codira index --full --json` in this repository.
- [ ] Verify `codira ctx "package metadata rename" --json` in this repository.
- [ ] Verify plugin discovery from installed artifacts, not source-tree
  leakage.

Exit criteria:

- [ ] Required repository checks pass.
- [ ] Build and install rehearsals pass.
- [ ] The installed CLI and plugin discovery work outside the source tree.

## Phase 8 - Create Fresh Public History

Goal:
Publish a clean `codira` history without old `repoindex` commit history.

Tasks:

- [ ] Remove old `.git` metadata only in the prepared `codira` copy, not in the
  source `repoindex` repository.
- [ ] Run `git init` in the prepared `codira` copy.
- [ ] Create one initial commit containing the fully renamed, validated tree.
- [ ] Add the new `codira` GitHub remote.
- [ ] Push `main`.
- [ ] Create and push tag `v1.0.0`.

Exit criteria:

- [ ] The public `codira` repository starts from the renamed tree.
- [ ] The first public tag is `v1.0.0`.

## Phase 9 - Transfer Selected Issues

Goal:
Move only intentionally active issue work to `codira`.

Tasks:

- [ ] Transfer selected open issues from `repoindex` to `codira`.
- [ ] Verify transferred issues have comments and assignees.
- [ ] Verify labels and milestones are preserved where intended.
- [ ] Verify old issue URLs redirect to the transferred issues where GitHub
  supports that redirect.

Exit criteria:

- [ ] Active issue work lives in `codira`.
- [ ] Historical issue work remains in `repoindex`.

## Phase 10 - Archive The Old Repository

Goal:
Freeze the old identity as historical reference.

Tasks:

- [ ] Update the old `repoindex` README with:
  - [ ] archived status
  - [ ] link to the new `codira` repository
  - [ ] note that active development moved to `codira`
  - [ ] note that the rename avoided conflict and confusion around the old
    `repoindex` package identity
- [ ] Archive the old `repoindex` repository on GitHub.
- [ ] Keep the old repository public.

Exit criteria:

- [ ] Old history and issues remain visible.
- [ ] Users landing on the old repository can find `codira`.

## Phase 11 - TestPyPI Rehearsal

Goal:
Prove the package set resolves from a package index before touching real PyPI.

Publish to TestPyPI in dependency order:

1. [ ] `codira-analyzer-python`
2. [ ] `codira-analyzer-json`
3. [ ] `codira-analyzer-c`
4. [ ] `codira-analyzer-bash`
5. [ ] `codira-backend-sqlite`
6. [ ] `codira`
7. [ ] `codira-bundle-official`

Fresh-environment checks:

- [ ] `pip install codira-bundle-official` from TestPyPI with PyPI as the
  extra index for third-party dependencies.
- [ ] `codira --help`
- [ ] `codira -V`
- [ ] `codira plugins --json`
- [ ] `codira index --full --json`
- [ ] `codira ctx "package metadata rename" --json`
- [ ] Confirm no installed distribution depends on `repoindex`.

Exit criteria:

- [ ] TestPyPI install and runtime smoke tests pass from a fresh environment.

## Phase 12 - Real PyPI Release

Goal:
Publish the validated `codira` package set to PyPI.

Publish to PyPI in dependency order:

1. [ ] `codira-analyzer-python`
2. [ ] `codira-analyzer-json`
3. [ ] `codira-analyzer-c`
4. [ ] `codira-analyzer-bash`
5. [ ] `codira-backend-sqlite`
6. [ ] `codira`
7. [ ] `codira-bundle-official`

Tasks:

- [ ] Do not publish the bundle before its dependencies exist on PyPI.
- [ ] Do not reuse any failed version number in a package namespace.
- [ ] Verify each PyPI project page after upload.
- [ ] Verify `pip install codira-bundle-official` in a fresh environment.
- [ ] Verify `codira --help`.
- [ ] Verify `codira plugins --json`.
- [ ] Verify no dependency metadata points to `repoindex`.

Exit criteria:

- [ ] The real PyPI release is installable through `codira-bundle-official`.
- [ ] The installed command is `codira`.
- [ ] The installed public API is `codira*`.

## Phase 13 - Post-Release Cleanup

Goal:
Remove local migration leftovers and update downstream references.

Tasks:

- [ ] Verify GitHub README badges and install instructions.
- [ ] Verify published documentation links.
- [ ] Verify release notes mention the rebrand and version reset.
- [ ] Update local developer aliases and shell snippets.
- [ ] Update any external documentation controlled by the maintainer.
- [ ] Remove temporary release notebooks or archive them under `docs/process`
  if they are still useful.
- [ ] Run one final stale-reference audit.

Exit criteria:

- [ ] The migration is complete.
- [ ] Remaining `repoindex` references are historical and intentional.

## Validation Contract

Every implementation slice must end with the repository contract unless the
slice only changes planning documentation.

Repository contract:

```bash
source .venv/bin/activate
black --check src scripts tests
ruff check src scripts tests
mypy src scripts tests
pytest -q
```

Rename-sensitive slices must also validate the relevant package and example
paths.

## Commit Policy

Use small atomic commits while implementing the migration. Each commit should
leave the tree in a coherent state and should update this ledger when it
completes a listed step.

Do not combine unrelated behavior changes with the rebrand unless they are
required to keep `repoindex` or `codira` usable as a tool during migration.
