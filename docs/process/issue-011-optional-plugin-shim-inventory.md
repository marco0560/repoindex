# Issue 011 Optional Plugin Shim Inventory

## Purpose

This note records the remaining compatibility surfaces for the extracted
first-party optional analyzer packages during Phase 1 of the package-boundary
migration.

It exists to make the transition explicit: the current shims are accepted for
the monorepo contributor workflow, but they are not the intended end state.

## Scope

This inventory covers the extracted first-party optional analyzers only:

- `repoindex-analyzer-c`
- `repoindex-analyzer-bash`

It does not cover the future default-implementation extraction planned for
issue `#12`.

## Current Compatibility Surfaces

### `src/repoindex/analyzers/c.py`

Role:

- preserves historical imports from `repoindex.analyzers.c`
- attempts to import `repoindex_analyzer_c`
- falls back to prepending `packages/repoindex-analyzer-c/src` to `sys.path`
  when running inside the current monorepo checkout
- raises a deterministic install hint when the extracted package is absent

Status:

- accepted as a Phase 1 compatibility shim
- must not regain implementation ownership

### `src/repoindex/analyzers/bash.py`

Role:

- preserves historical imports from `repoindex.analyzers.bash`
- attempts to import `repoindex_analyzer_bash`
- falls back to prepending `packages/repoindex-analyzer-bash/src` to `sys.path`
  when running inside the current monorepo checkout
- raises a deterministic install hint when the extracted package is absent

Status:

- accepted as a Phase 1 compatibility shim
- must not regain implementation ownership

### `src/repoindex/analyzers/__init__.py`

Role:

- re-exports core analyzers directly
- conditionally re-exports `CAnalyzer` and `BashAnalyzer` through the shim
  modules when those extracted packages are importable

Status:

- accepted as a narrow package-surface compatibility layer
- should stay lightweight and import-only

### `src/repoindex/registry.py`

Role:

- treats `repoindex.analyzers.c` and `repoindex.analyzers.bash` as optional
  built-in factory import targets
- relies on the shim modules to bridge current monorepo contributor installs to
  extracted first-party analyzer packages

Status:

- accepted for Phase 1 because it keeps registry behavior stable while package
  ownership moves out of core
- should stop depending on monorepo-local bridging once issue `#13` lands

## Accepted Phase 1 Rule

These shims are allowed only to preserve compatibility and contributor
ergonomics during the monorepo transition.

They must remain:

- narrow
- import-only
- deterministic
- explicitly documented as temporary

They must not:

- reintroduce analyzer implementation logic into core
- become the primary discovery mechanism for published installs
- hide missing-package failures without an operator-facing message

## Removal Target

The removal target for these shims remains issue `#13`.

That cleanup should happen only after:

- issue `#11` completes the Phase 1 package-boundary reconciliation
- issue `#12` completes the default-implementation extraction
- the multirepo split removes the need for sibling-source loading

At that point, installed package metadata and entry points become the only
supported discovery path for the extracted first-party analyzers.
