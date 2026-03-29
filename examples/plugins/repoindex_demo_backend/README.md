# repoindex-demo-backend

Example third-party backend plugin for `repoindex`.

This package subclasses the built-in SQLite backend so it can be installed and
discovered through the same plugin contract as an out-of-tree backend.

## Install

```bash
source /path/to/repoindex/.venv/bin/activate
pip install -e /path/to/repoindex/examples/plugins/repoindex_demo_backend
```

## Verify

```bash
repoindex plugins
REPOINDEX_INDEX_BACKEND=demo-backend repoindex index
```
