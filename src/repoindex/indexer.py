from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.parser_ast import parse_file
from repoindex.scanner import file_metadata, iter_python_files
from repoindex.storage import get_db_path


def index_repo(root: Path) -> None:
    db_path = get_db_path(root)
    conn = sqlite3.connect(db_path)

    try:
        for path in iter_python_files(root):
            meta = file_metadata(path)

            cur = conn.execute(
                "INSERT OR REPLACE INTO files(path, hash, mtime, size) VALUES (?, ?, ?, ?)",
                (meta["path"], meta["hash"], meta["mtime"], meta["size"]),
            )

            file_id = cur.lastrowid

            parsed = parse_file(path)

            cur = conn.execute(
                "INSERT INTO modules(file_id, name, docstring, has_docstring) VALUES (?, ?, ?, ?)",
                (
                    file_id,
                    parsed["module"]["name"],
                    parsed["module"]["docstring"],
                    parsed["module"]["has_docstring"],
                ),
            )

            module_id = cur.lastrowid

            for cls in parsed["classes"]:
                conn.execute(
                    "INSERT INTO classes(module_id, name, lineno, end_lineno, docstring, has_docstring) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        module_id,
                        cls["name"],
                        cls["lineno"],
                        cls["end_lineno"],
                        cls["docstring"],
                        cls["has_docstring"],
                    ),
                )

            for fn in parsed["functions"]:
                conn.execute(
                    "INSERT INTO functions(module_id, class_id, name, lineno, end_lineno, signature, docstring, has_docstring, is_method, is_public) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        module_id,
                        None,
                        fn["name"],
                        fn["lineno"],
                        fn["end_lineno"],
                        "",
                        fn["docstring"],
                        fn["has_docstring"],
                        fn["is_method"],
                        fn["is_public"],
                    ),
                )

            for imp in parsed["imports"]:
                conn.execute(
                    "INSERT INTO imports(module_id, name, alias, lineno) VALUES (?, ?, ?, ?)",
                    (
                        module_id,
                        imp["name"],
                        imp["alias"],
                        imp["lineno"],
                    ),
                )

        conn.commit()
    finally:
        conn.close()
