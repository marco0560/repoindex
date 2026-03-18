from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.indexer import index_repo
from repoindex.query.exact import docstring_issues, find_symbol
from repoindex.storage import get_db_path, init_db


def test_index_and_queries(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()

    source = pkg / "sample.py"
    source.write_text(
        '"""Module doc."""\n'
        "\n"
        "class Demo:\n"
        "    def method(self):\n"
        "        return 1\n"
        "\n"
        "def public_func(x):\n"
        '    """Do work."""\n'
        "    return x\n",
        encoding="utf-8",
    )

    init_db(tmp_path)
    index_repo(tmp_path)

    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        function_count = conn.execute("SELECT COUNT(*) FROM functions").fetchone()[0]
        class_count = conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0]
    finally:
        conn.close()

    assert function_count == 2
    assert class_count == 1

    demo_rows = find_symbol(tmp_path, "Demo")
    assert len(demo_rows) == 1

    issues = docstring_issues(tmp_path)
    messages = [message for _issue_type, message in issues]
    assert any(
        "Method Demo.method: Missing docstring" == message for message in messages
    )
