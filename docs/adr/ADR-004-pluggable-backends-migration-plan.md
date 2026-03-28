# ADR-004 — Pluggable Backend and Analyzer Migration Plan

**Date:** 28/03/2026
**Status:** Accepted

## Context

`repoindex` currently has a strong implicit coupling between:

* Python-specific analysis
* SQLite-specific persistence and query execution
* CLI/query surfaces that directly depend on SQLite-oriented helpers

Open issues make the next architectural direction explicit:

* issue `#1` requires a cleaner persistence boundary for embeddings and their
  invalidation metadata
* issue `#2` requires pluggable language analyzers so multi-language
  repositories become a first-class target

The migration needs to preserve determinism and maintainability while
expanding architecture documentation, not just implementation code.

## Decision

Adopt a two-family plugin architecture and execute the migration on a dedicated
branch through a sequence of small, reviewable commits.

### Plugin Families

`repoindex` will distinguish two separate extension families:

* `IndexBackend`
  Exactly one storage/query backend is active for a given repository index.
* `LanguageAnalyzer`
  Multiple analyzers may be active in the same indexing run so one repository
  can be indexed across multiple languages and dialects.

This asymmetry is intentional:

* storage is an instance-level policy decision
* analyzers are repository-content capabilities

### Documentation and Tests Are First-Class

The migration is not code-only work.

Each architectural step must include, where applicable:

* tests that freeze or extend behavior
* architecture documentation updates
* ADRs for durable decisions that would otherwise be lost in commit history

The documentation scope must expand beyond README usage notes to include:

* architecture overviews
* pipeline documentation
* plugin model documentation
* backend/analyzer extension guidance
* ADRs that preserve and enforce decision history

## Rationale

One active backend per instance avoids a large class of unnecessary complexity:

* competing schema ownership
* inconsistent migration rules
* duplicate query semantics
* split incremental reuse logic
* ambiguous embedding persistence
* reduced determinism

Allowing multiple analyzers in one run is necessary for mixed-language
repositories and is aligned with the explicit goal of supporting them without
treating non-Python files as unsupported noise.

Treating tests and architecture documentation as first-class citizens reduces
the risk that the refactor drifts into undocumented framework churn.

## Consequences

### Positive

* clear separation between language analysis and persistence concerns
* explicit support for mixed-language repositories
* deterministic architectural boundaries for future backend and analyzer work
* durable design history through ADRs
* smaller and safer implementation increments

### Negative

* more upfront design and documentation work before user-visible feature
  expansion
* more commits and branch management overhead
* stronger discipline required to keep the execution ledger current

### Neutral / Trade-offs

* README updates should follow architecture stabilization, not lead it
* some migration phases may need more than one commit to keep changes atomic
* additional ADRs may be created as the migration reveals narrower decisions

## Migration Plan

The migration will proceed through the following phases.

### Phase 1 — Branch and Architecture Skeleton

Create a dedicated branch for this migration.

Add an architecture documentation skeleton covering:

* system overview
* indexing pipeline
* query pipeline
* plugin model
* storage backends
* language analyzers

Add an ADR template if one does not already exist.

### Phase 2 — Characterization Tests

Add or extend tests that freeze current behavior for:

* `index`
* `symbol`
* `calls`
* `refs`
* `embeddings`
* `context-for`
* incremental reuse
* embedding invalidation
* deterministic ordering

These tests are guardrails for the refactor, not optional cleanup.

### Phase 3 — Core Contracts and Normalized Artifacts

Introduce backend-neutral contracts and data structures for:

* `LanguageAnalyzer`
* `AnalysisResult`
* `IndexBackend`
* normalized index artifacts

Document the responsibilities and invariants of those contracts.

Create additional ADRs if symbol identity, artifact ownership, or extension
metadata boundaries require durable decisions.

### Phase 4 — SQLite Backend Encapsulation

Wrap the current SQLite implementation behind a concrete `SQLiteIndexBackend`
without changing observable CLI behavior.

Keep schema semantics stable during this phase.

Add backend contract tests that SQLite must satisfy.

### Phase 5 — Indexer Orchestration Refactor

Refactor `index_repo` into an orchestrator that:

* discovers files
* routes files to analyzers
* collects normalized artifacts
* delegates persistence to the selected backend

The orchestrator must stop depending directly on Python parser internals and
raw storage implementation details.

### Phase 6 — Python Analyzer Extraction

Extract the existing Python-specific logic into a `PythonAnalyzer`.

This includes:

* parsing
* symbol extraction
* call extraction
* callable-reference extraction
* import handling
* docstring audit integration

### Phase 7 — Query Abstraction

Refactor exact-query and embedding-query paths so they depend on backend
interfaces rather than raw SQLite access.

Preserve current CLI output contracts.

Add shared query contract tests where practical.

### Phase 8 — Registries and Configuration

Introduce registry and configuration mechanisms so:

* one backend is selected for the index
* multiple analyzers can be registered and activated by file routing

Document defaults, selection rules, and failure behavior.

Create an ADR if configuration semantics become materially architectural.

### Phase 9 — Second Analyzer Proof

Add one non-Python analyzer to validate the abstraction.

C is the preferred first candidate.

The first non-Python analyzer should prioritize:

* symbol extraction
* dependency extraction
* deterministic mixed-language indexing behavior

### Phase 10 — Final Documentation Consolidation

Expand and reconcile the documentation set so contributors can reconstruct the
architecture and the decisions behind it.

This phase should leave behind:

* stable architecture documents
* updated contributor guidance
* updated README references
* a complete ADR trail for the major choices made during the migration

## Execution Rules

* Use a dedicated branch for the migration.
* Make multiple commits, with at least one commit per phase.
* Split large phases into smaller atomic commits when needed.
* Keep tests and documentation in-scope for every phase.
* Preserve deterministic behavior unless a later ADR explicitly changes it.

## Phase Ledger

Mark each phase as work lands.

* [ ] Phase 1 — Branch and Architecture Skeleton
* [ ] Phase 2 — Characterization Tests
* [ ] Phase 3 — Core Contracts and Normalized Artifacts
* [ ] Phase 4 — SQLite Backend Encapsulation
* [ ] Phase 5 — Indexer Orchestration Refactor
* [ ] Phase 6 — Python Analyzer Extraction
* [ ] Phase 7 — Query Abstraction
* [ ] Phase 8 — Registries and Configuration
* [ ] Phase 9 — Second Analyzer Proof
* [ ] Phase 10 — Final Documentation Consolidation

## Notes

Expected follow-up ADR topics include:

* one active backend per repository instance
* multiple analyzers per indexing run
* normalized artifact model and symbol identity
* embedding persistence and invalidation ownership
* query surfaces depending on backend contracts rather than backend internals
