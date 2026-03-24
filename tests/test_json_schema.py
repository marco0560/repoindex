"""Schema contract tests for JSON context rendering."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import validate

from repoindex.indexer import index_repo
from repoindex.query.context import context_for
from repoindex.storage import init_db


def _load_schema(root: Path) -> dict[str, object]:
    """
    Load the JSON schema used for context output validation.

    Parameters
    ----------
    root : pathlib.Path
        Repository root containing the schema file.

    Returns
    -------
    dict[str, object]
        Parsed JSON schema document.
    """
    schema_path = root / "src" / "repoindex" / "schema" / "context.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def test_context_output_matches_schema(tmp_path: Path) -> None:
    """
    Validate that JSON output of context_for conforms to the JSON schema.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest. The fixture is unused but
        retained for symmetry with the companion schema test.

    Returns
    -------
    None
        The test asserts schema conformance for the populated case.

    Notes
    -----
    This is a structural contract test that keeps the schema and renderer in
    sync and prevents silent drift in the JSON output shape.
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

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory provided by pytest. The fixture is unused but
        retained for interface consistency with the companion test.

    Returns
    -------
    None
        The test asserts schema conformance for the no-match case.
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
