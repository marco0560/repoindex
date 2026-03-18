from __future__ import annotations

import sqlite3
from pathlib import Path

from repoindex.parser_ast import parse_file
from repoindex.scanner import file_metadata, iter_python_files
from repoindex.storage import get_db_path


def _clear_index_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM docstring_issues")
    conn.execute("DELETE FROM symbol_index")
    conn.execute("DELETE FROM imports")
    conn.execute("DELETE FROM functions")
    conn.execute("DELETE FROM classes")
    conn.execute("DELETE FROM modules")
    conn.execute("DELETE FROM files")


def index_repo(root: Path) -> None:
    db_path = get_db_path(root)
    conn = sqlite3.connect(db_path)

    try:
        _clear_index_tables(conn)

        for path in sorted(iter_python_files(root)):
            meta = file_metadata(path)

            cur = conn.execute(
                "INSERT INTO files(path, hash, mtime, size) VALUES (?, ?, ?, ?)",
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

            conn.execute(
                "INSERT INTO symbol_index(name, type, module_name, file_path, lineno) VALUES (?, ?, ?, ?, ?)",
                (
                    parsed["module"]["name"],
                    "module",
                    parsed["module"]["name"],
                    meta["path"],
                    1,
                ),
            )

            if not parsed["module"]["has_docstring"]:
                conn.execute(
                    "INSERT INTO docstring_issues(function_id, class_id, module_id, issue_type, message) VALUES (?, ?, ?, ?, ?)",
                    (
                        None,
                        None,
                        module_id,
                        "missing",
                        f"Module {parsed['module']['name']} is missing a docstring",
                    ),
                )

            for cls in parsed["classes"]:
                cur = conn.execute(
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
                class_id = cur.lastrowid

                conn.execute(
                    "INSERT INTO symbol_index(name, type, module_name, file_path, lineno) VALUES (?, ?, ?, ?, ?)",
                    (
                        cls["name"],
                        "class",
                        parsed["module"]["name"],
                        meta["path"],
                        cls["lineno"],
                    ),
                )

                if not cls["has_docstring"]:
                    conn.execute(
                        "INSERT INTO docstring_issues(function_id, class_id, module_id, issue_type, message) VALUES (?, ?, ?, ?, ?)",
                        (
                            None,
                            class_id,
                            None,
                            "missing",
                            f"Class {cls['name']} is missing a docstring",
                        ),
                    )

                for method in cls["methods"]:
                    cur = conn.execute(
                        "INSERT INTO functions(module_id, class_id, name, lineno, end_lineno, signature, docstring, has_docstring, is_method, is_public) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            module_id,
                            class_id,
                            method["name"],
                            method["lineno"],
                            method["end_lineno"],
                            method["signature"],
                            method["docstring"],
                            method["has_docstring"],
                            method["is_method"],
                            method["is_public"],
                        ),
                    )
                    function_id = cur.lastrowid

                    conn.execute(
                        "INSERT INTO symbol_index(name, type, module_name, file_path, lineno) VALUES (?, ?, ?, ?, ?)",
                        (
                            method["name"],
                            "method",
                            parsed["module"]["name"],
                            meta["path"],
                            method["lineno"],
                        ),
                    )

                    if not method["has_docstring"]:
                        conn.execute(
                            "INSERT INTO docstring_issues(function_id, class_id, module_id, issue_type, message) VALUES (?, ?, ?, ?, ?)",
                            (
                                function_id,
                                None,
                                None,
                                "missing",
                                f"Method {cls['name']}.{method['name']} is missing a docstring",
                            ),
                        )

            for fn in parsed["functions"]:
                cur = conn.execute(
                    "INSERT INTO functions(module_id, class_id, name, lineno, end_lineno, signature, docstring, has_docstring, is_method, is_public) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        module_id,
                        None,
                        fn["name"],
                        fn["lineno"],
                        fn["end_lineno"],
                        fn["signature"],
                        fn["docstring"],
                        fn["has_docstring"],
                        fn["is_method"],
                        fn["is_public"],
                    ),
                )
                function_id = cur.lastrowid

                conn.execute(
                    "INSERT INTO symbol_index(name, type, module_name, file_path, lineno) VALUES (?, ?, ?, ?, ?)",
                    (
                        fn["name"],
                        "function",
                        parsed["module"]["name"],
                        meta["path"],
                        fn["lineno"],
                    ),
                )

                if not fn["has_docstring"]:
                    conn.execute(
                        "INSERT INTO docstring_issues(function_id, class_id, module_id, issue_type, message) VALUES (?, ?, ?, ?, ?)",
                        (
                            function_id,
                            None,
                            None,
                            "missing",
                            f"Function {fn['name']} is missing a docstring",
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
