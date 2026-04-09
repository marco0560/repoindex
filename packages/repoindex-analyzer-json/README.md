# repoindex-analyzer-json

First-party JSON analyzer plugin for `repoindex`.

Repository-local editable install:

```bash
source .venv/bin/activate
pip install -e ../repoindex
pip install -e ../repoindex/packages/repoindex-analyzer-json
```

After installation, verify discovery with:

```bash
repoindex plugins
repoindex coverage
```

Package-local verification:

```bash
pytest -q packages/repoindex-analyzer-json/tests
```
