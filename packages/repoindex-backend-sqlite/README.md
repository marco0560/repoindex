# repoindex-backend-sqlite

First-party SQLite backend plugin for `repoindex`.

Repository-local editable install:

```bash
source .venv/bin/activate
pip install -e ../repoindex
pip install -e ../repoindex/packages/repoindex-backend-sqlite
```

After installation, verify discovery with:

```bash
repoindex plugins
repoindex embeddings "symbol lookup" --json
```

Package-local verification:

```bash
pytest -q packages/repoindex-backend-sqlite/tests
```
