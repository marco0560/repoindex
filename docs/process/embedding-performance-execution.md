# Embedding Performance Execution

## Purpose

This branch-local ledger records the executed steps for the batched embedding
performance workstream.

## Branch

The implementation branch for this work is:

```text
feat/batch-embedding-indexing
```

## Planned Phases

1. Branch bootstrap and execution ledger
2. ADR for batched embeddings and tunable runtime controls
3. Batched embedding backend implementation
4. Same-run payload deduplication in index persistence
5. Benchmark script and operator documentation
6. Validation, tuning review, and commit preparation

## Executed Steps

* [x] Created the dedicated implementation branch.
* [x] Added the branch-local execution ledger.
* [x] Added ADR-008 covering batching, same-run payload reuse, and explicit
  runtime controls.
* [x] Added a batched embedding API and environment-driven runtime settings.
* [x] Updated index persistence to batch recomputed embeddings and reuse
  identical payload vectors within one flush.
* [x] Added regression tests for batching and same-run payload reuse.
* [x] Added a benchmark script for phase timings and embedding batch metrics.
* [x] Ran the full validation surface:
  `black --check src scripts tests`,
  `ruff check src scripts tests`,
  `mypy src scripts tests`,
  `pytest -q`.
* [x] Captured one instrumented full-index benchmark on this repository. The
  first sample showed `embed_texts` and `flush_embedding_rows` dominating wall
  time, which confirmed the optimization target.
* [x] Ran controlled embedding microbenchmarks after the first pass. On this
  host, constrained Torch threads and larger batches sometimes helped on the
  synthetic benchmark.
* [x] Kept runtime tuning operator-controlled after follow-up end-to-end
  measurements proved too noisy to justify hardcoded thread defaults in this
  branch.
* [x] Create the final branch commit.
