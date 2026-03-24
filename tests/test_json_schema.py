from __future__ import annotations

import json
from pathlib import Path

from jsonschema import validate

from repoindex.indexer import index_repo
from repoindex.query.context import context_for
from repoindex.storage import init_db


def _load_schema(root: Path) -> dict[str, object]:
    schema_path = root / "src" / "repoindex" / "schema" / "context.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def test_context_output_matches_schema(tmp_path: Path) -> None:
    """
    Validate that JSON output of context_for conforms to the JSON schema.

    This is a structural contract test:
    - ensures schema and renderer stay in sync
    - prevents silent drift
    """
    root = Path.cwd()

    schema = _load_schema(root)
    init_db(root)
    index_repo(root)

    # Use a stable query that always produces results
    output = context_for(
        root,
        "validate docstring",
        as_json=True,
        explain=True,
    )

    data = json.loads(output)

    validate(instance=data, schema=schema)


def test_context_no_matches_schema(tmp_path: Path) -> None:
    """
    Validate schema compliance for the 'no_matches' case.
    """
    root = Path.cwd()
    schema = _load_schema(root)
    init_db(root)
    index_repo(root)

    output = context_for(
        root,
        "zzzzzzzzzzzzzzzzzzzzzz",  # unlikely to match anything
        as_json=True,
        explain=True,
    )

    data = json.loads(output)

    validate(instance=data, schema=schema)
