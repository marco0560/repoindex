# Quick Start

The smallest plugin package needs:

1. a normal Python package
2. a dependency on `repoindex`
3. one entry point in either `repoindex.analyzers` or `repoindex.backends`
4. a zero-argument callable that returns a plugin instance

If you want a copyable starting point instead of writing from scratch, begin
with one of these example packages:

- `examples/plugins/repoindex_demo_analyzer`
- `examples/plugins/repoindex_demo_backend`

Minimal analyzer package skeleton:

```toml
[project]
name = "repoindex-demo-analyzer"
version = "0.1.0"
dependencies = ["repoindex"]

[project.entry-points."repoindex.analyzers"]
demo = "repoindex_demo_analyzer:build_analyzer"
```

Minimal backend package skeleton:

```toml
[project]
name = "repoindex-demo-backend"
version = "0.1.0"
dependencies = ["repoindex"]

[project.entry-points."repoindex.backends"]
demo = "repoindex_demo_backend:build_backend"
```

After installation:

```bash
pip install -e /path/to/your/plugin
repoindex plugins
repoindex coverage
```

If discovery fails, `repoindex plugins` shows whether the plugin was:

- loaded
- skipped
- rejected as a duplicate

Use `repoindex coverage` to verify whether the current analyzer set fully
covers tracked files under `src/`, `tests/`, and `scripts/`. If you want to
block partial indexing runs, use:

```bash
repoindex index --require-full-coverage
```
