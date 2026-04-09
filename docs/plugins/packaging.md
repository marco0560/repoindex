# Packaging And Install

Plugin discovery uses standard Python entry points.

Current groups:

- `repoindex.analyzers`
- `repoindex.backends`

Install model:

- `repoindex` core stays installable on its own
- third-party plugins are separate distributions
- official first-party plugins also use separate distributions under `packages/`
- plugins are discovered from the current Python environment
- `repoindex plugins` reports `origin=core`, `origin=first_party`, or
  `origin=third_party` to clarify ownership

Typical local workflow:

```bash
source .venv/bin/activate
pip install -e ../repoindex
pip install -e ../repoindex/packages/repoindex-analyzer-c
pip install -e ../repoindex/packages/repoindex-analyzer-bash
pip install -e /path/to/repoindex-demo-analyzer
repoindex plugins
```

Copyable example distributions live under:

- `examples/plugins/repoindex_demo_analyzer`
- `examples/plugins/repoindex_demo_backend`

Repository-owned first-party distributions now live under:

- `packages/repoindex-analyzer-c`
- `packages/repoindex-analyzer-bash`
- `packages/repoindex-bundle-official`

The authoritative repository-local editable install set for those packages is
defined by:

```bash
python scripts/install_first_party_packages.py
```

The accepted published umbrella install name for the curated official set is
`repoindex[bundle-official]`. During the current monorepo phase, repository
contributors still install the extracted packages from `packages/`.

For optional dependencies inside a plugin package, declare them in the plugin's
own `pyproject.toml`. The core package should not need to know about them.

If a plugin fails to load, `repoindex plugins` reports the failure without
requiring you to inspect internal registry code.
