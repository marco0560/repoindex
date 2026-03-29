# Packaging And Install

Plugin discovery uses standard Python entry points.

Current groups:

- `repoindex.analyzers`
- `repoindex.backends`

Install model:

- `repoindex` core stays installable on its own
- third-party plugins are separate distributions
- plugins are discovered from the current Python environment

Typical local workflow:

```bash
source .venv/bin/activate
pip install -e ../repoindex
pip install -e /path/to/repoindex-demo-analyzer
repoindex plugins
```

Copyable example distributions live under:

- `examples/plugins/repoindex_demo_analyzer`
- `examples/plugins/repoindex_demo_backend`

For optional dependencies inside a plugin package, declare them in the plugin's
own `pyproject.toml`. The core package should not need to know about them.

If a plugin fails to load, `repoindex plugins` reports the failure without
requiring you to inspect internal registry code.
