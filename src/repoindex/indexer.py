"""Index repository symbols and docstring diagnostics into SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

from repoindex.docstring import validate_docstring
from repoindex.parser_ast import parse_file
from repoindex.scanner import file_metadata, iter_project_files
from repoindex.storage import get_db_path

CallRecord = dict[str, str | int]


def _clear_index_tables(conn: sqlite3.Connection) -> None:
    """
    Remove all indexed rows from the database tables.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection to clear in place.

    Returns
    -------
    None
        The tables are cleared in place on ``conn``.
    """
    conn.execute("DELETE FROM docstring_issues")
    conn.execute("DELETE FROM call_edges")
    conn.execute("DELETE FROM symbol_index")
    conn.execute("DELETE FROM imports")
    conn.execute("DELETE FROM functions")
    conn.execute("DELETE FROM classes")
    conn.execute("DELETE FROM modules")
    conn.execute("DELETE FROM files")


def _qualified_callable_name(name: str, class_name: str | None = None) -> str:
    """
    Build the logical name used for call-graph identity.

    Parameters
    ----------
    name : str
        Unqualified function or method name.
    class_name : str | None, optional
        Owning class name for methods.

    Returns
    -------
    str
        ``Class.method`` for methods and the bare function name otherwise.
    """
    if class_name is None:
        return name
    return f"{class_name}.{name}"


def _import_alias_map(imports: list[dict[str, object]]) -> dict[str, str]:
    """
    Build a deterministic alias map for imported names.

    Parameters
    ----------
    imports : list[dict[str, object]]
        Parsed import rows from a module.

    Returns
    -------
    dict[str, str]
        Mapping from the locally bound import name to the imported dotted
        target.
    """
    aliases: dict[str, str] = {}

    for imp in imports:
        imported = str(imp["name"])
        alias = imp["alias"]
        local_name = str(alias) if alias is not None else imported.split(".")[-1]

        if "." in imported and alias is None and "." not in local_name:
            aliases[imported] = imported

        aliases[local_name] = imported

    return aliases


def _resolve_imported_function(
    imported: str,
    module_functions: dict[str, set[str]],
) -> tuple[str, str] | None:
    """
    Resolve a directly imported same-repo function target.

    Parameters
    ----------
    imported : str
        Imported dotted target as recorded by the parser.
    module_functions : dict[str, set[str]]
        Known top-level functions keyed by module name.

    Returns
    -------
    tuple[str, str] | None
        Resolved ``(callee_module, callee_name)`` pair, or ``None`` when the
        import does not name a straightforward same-repo function.
    """
    if "." not in imported:
        return None

    module_name, function_name = imported.rsplit(".", 1)
    if function_name in module_functions.get(module_name, set()):
        return (module_name, function_name)
    return None


def _resolve_module_attribute_call(
    base: str,
    target: str,
    import_aliases: dict[str, str],
    module_functions: dict[str, set[str]],
) -> tuple[str, str] | None:
    """
    Resolve a module-qualified same-repo function call.

    Parameters
    ----------
    base : str
        Static base expression of the attribute call.
    target : str
        Attribute name being called.
    import_aliases : dict[str, str]
        Mapping of locally bound import names to imported dotted targets.
    module_functions : dict[str, set[str]]
        Known top-level functions keyed by module name.

    Returns
    -------
    tuple[str, str] | None
        Resolved ``(callee_module, callee_name)`` pair, or ``None`` when the
        call cannot be resolved conservatively.
    """
    imported = import_aliases.get(base)
    if imported is None:
        return None

    if target in module_functions.get(imported, set()):
        return (imported, target)
    return None


def _resolve_call_record(
    call: dict[str, str | int],
    *,
    caller_module: str,
    caller_class: str | None,
    import_aliases: dict[str, str],
    module_functions: dict[str, set[str]],
    class_methods: dict[tuple[str, str], set[str]],
) -> tuple[str | None, str | None, int]:
    """
    Resolve one parsed call-site record into a stored call edge.

    Parameters
    ----------
    call : dict[str, str | int]
        Parsed call-site record.
    caller_module : str
        Module containing the caller.
    caller_class : str | None
        Owning class for method callers.
    import_aliases : dict[str, str]
        Mapping of locally bound import names to imported dotted targets.
    module_functions : dict[str, set[str]]
        Known top-level functions keyed by module name.
    class_methods : dict[tuple[str, str], set[str]]
        Known method names keyed by ``(module_name, class_name)``.

    Returns
    -------
    tuple[str | None, str | None, int]
        ``(callee_module, callee_name, resolved)`` for the call edge.
    """
    kind = str(call.get("kind", "unresolved"))
    target = str(call.get("target", ""))

    candidates: set[tuple[str, str]] = set()

    if kind == "name" and target:
        imported = import_aliases.get(target)
        if imported is not None:
            resolved_import = _resolve_imported_function(imported, module_functions)
            if resolved_import is not None:
                candidates.add(resolved_import)

        if target in module_functions.get(caller_module, set()):
            candidates.add((caller_module, target))

    elif kind == "attribute" and target:
        base = str(call.get("base", ""))
        if caller_class is not None and base in {"self", "cls"}:
            methods = class_methods.get((caller_module, caller_class), set())
            if target in methods:
                candidates.add(
                    (caller_module, _qualified_callable_name(target, caller_class))
                )

        resolved_module_call = _resolve_module_attribute_call(
            base,
            target,
            import_aliases,
            module_functions,
        )
        if resolved_module_call is not None:
            candidates.add(resolved_module_call)

    if len(candidates) == 1:
        callee_module, callee_name = next(iter(candidates))
        return (callee_module, callee_name, 1)

    return (None, None, 0)


def index_repo(root: Path) -> None:
    """
    Scan repository files and populate the SQLite index.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose tracked Python files should be indexed.

    Returns
    -------
    None
        The repository index is rebuilt in place.

    Notes
    -----
    The function clears all indexed tables before repopulating them, so each
    run produces a fresh snapshot of the current repository state.
    """
    db_path = get_db_path(root)
    conn = sqlite3.connect(db_path)

    try:
        _clear_index_tables(conn)

        parsed_files: list[tuple[Path, dict[str, object], dict[str, object]]] = []

        for path in iter_project_files(root):
            parsed_files.append((path, file_metadata(path), parse_file(path, root)))

        module_functions: dict[str, set[str]] = {}
        class_methods: dict[tuple[str, str], set[str]] = {}

        for _path, _meta, parsed in parsed_files:
            module = cast(dict[str, object], parsed["module"])
            functions = cast(list[dict[str, object]], parsed["functions"])
            classes = cast(list[dict[str, object]], parsed["classes"])

            module_name = str(module["name"])
            module_functions[module_name] = {str(fn["name"]) for fn in functions}

            for cls in classes:
                class_name = str(cls["name"])
                methods = cast(list[dict[str, object]], cls["methods"])
                class_methods[(module_name, class_name)] = {
                    str(method["name"]) for method in methods
                }

        for _path, meta, parsed in parsed_files:
            module = cast(dict[str, object], parsed["module"])
            classes = cast(list[dict[str, object]], parsed["classes"])
            functions = cast(list[dict[str, object]], parsed["functions"])
            imports = cast(list[dict[str, object]], parsed["imports"])

            cur = conn.execute(
                "INSERT INTO files(path, hash, mtime, size) VALUES (?, ?, ?, ?)",
                (meta["path"], meta["hash"], meta["mtime"], meta["size"]),
            )
            file_id = cur.lastrowid
            module_name = str(module["name"])

            cur = conn.execute(
                "INSERT INTO modules"
                "(file_id, name, docstring, has_docstring) VALUES (?, ?, ?, ?)",
                (
                    file_id,
                    module_name,
                    module["docstring"],
                    module["has_docstring"],
                ),
            )
            module_id = cur.lastrowid

            conn.execute(
                "INSERT INTO symbol_index"
                "(name, type, module_name, file_path, lineno) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    module_name,
                    "module",
                    module_name,
                    meta["path"],
                    1,
                ),
            )

            issues = validate_docstring(
                cast(str | None, module["docstring"]),
                is_public=1,
            )

            for issue_type, message in issues:
                conn.execute(
                    "INSERT INTO docstring_issues"
                    "(function_id, class_id, module_id, issue_type, message) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        None,
                        None,
                        module_id,
                        issue_type,
                        f"Module {module_name}: {message}",
                    ),
                )

            for cls in classes:
                methods = cast(list[dict[str, object]], cls["methods"])
                cur = conn.execute(
                    "INSERT INTO classes"
                    "(module_id, name, lineno, end_lineno, docstring, has_docstring) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
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
                    "INSERT INTO symbol_index"
                    "(name, type, module_name, file_path, lineno) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        cls["name"],
                        "class",
                        module_name,
                        meta["path"],
                        cls["lineno"],
                    ),
                )

                issues = validate_docstring(
                    cast(str | None, cls["docstring"]),
                    is_public=1,
                )

                for issue_type, message in issues:
                    conn.execute(
                        "INSERT INTO docstring_issues"
                        "(function_id, class_id, module_id, issue_type, message) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            None,
                            class_id,
                            None,
                            issue_type,
                            f"Class {cls['name']}: {message}",
                        ),
                    )

                for method in methods:
                    cur = conn.execute(
                        "INSERT INTO functions"
                        "(module_id, class_id, name, lineno, end_lineno, signature, "
                        "docstring, has_docstring, is_method, is_public) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        "INSERT INTO symbol_index"
                        "(name, type, module_name, file_path, lineno) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            method["name"],
                            "method",
                            module_name,
                            meta["path"],
                            method["lineno"],
                        ),
                    )

                    issues = validate_docstring(
                        cast(str | None, method["docstring"]),
                        cast(int, method["is_public"]),
                        parameters=cast(list[str], method["parameters"]),
                        require_callable_sections=True,
                        raises_exception=bool(method["raises"]),
                    )

                    for issue_type, message in issues:
                        conn.execute(
                            "INSERT INTO docstring_issues"
                            "(function_id, class_id, module_id, issue_type, message) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (
                                function_id,
                                None,
                                None,
                                issue_type,
                                f"Method {cls['name']}.{method['name']}: {message}",
                            ),
                        )

            for fn in functions:
                cur = conn.execute(
                    "INSERT INTO functions"
                    "(module_id, class_id, name, lineno, end_lineno, signature, "
                    "docstring, has_docstring, is_method, is_public) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    "INSERT INTO symbol_index"
                    "(name, type, module_name, file_path, lineno) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        fn["name"],
                        "function",
                        module_name,
                        meta["path"],
                        fn["lineno"],
                    ),
                )

                issues = validate_docstring(
                    cast(str | None, fn["docstring"]),
                    cast(int, fn["is_public"]),
                    parameters=cast(list[str], fn["parameters"]),
                    require_callable_sections=True,
                    raises_exception=bool(fn["raises"]),
                )

                for issue_type, message in issues:
                    conn.execute(
                        "INSERT INTO docstring_issues"
                        "(function_id, class_id, module_id, issue_type, message) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            function_id,
                            None,
                            None,
                            issue_type,
                            f"Function {fn['name']}: {message}",
                        ),
                    )

            for imp in imports:
                conn.execute(
                    "INSERT INTO imports(module_id, name, alias, lineno) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        module_id,
                        imp["name"],
                        imp["alias"],
                        imp["lineno"],
                    ),
                )

        edges: set[tuple[str, str, str | None, str | None, int]] = set()

        for _path, _meta, parsed in parsed_files:
            module = cast(dict[str, object], parsed["module"])
            functions = cast(list[dict[str, object]], parsed["functions"])
            classes = cast(list[dict[str, object]], parsed["classes"])
            imports = cast(list[dict[str, object]], parsed["imports"])

            caller_module = str(module["name"])
            import_aliases = _import_alias_map(imports)

            for fn in functions:
                caller_name = str(fn["name"])
                calls = cast(list[CallRecord], fn["calls"])
                for call in calls:
                    callee_module, callee_name, resolved = _resolve_call_record(
                        call,
                        caller_module=caller_module,
                        caller_class=None,
                        import_aliases=import_aliases,
                        module_functions=module_functions,
                        class_methods=class_methods,
                    )
                    edges.add(
                        (
                            caller_module,
                            caller_name,
                            callee_module,
                            callee_name,
                            resolved,
                        )
                    )

            for cls in classes:
                class_name = str(cls["name"])
                methods = cast(list[dict[str, object]], cls["methods"])
                for method in methods:
                    caller_name = _qualified_callable_name(
                        str(method["name"]),
                        class_name,
                    )
                    calls = cast(list[CallRecord], method["calls"])
                    for call in calls:
                        callee_module, callee_name, resolved = _resolve_call_record(
                            call,
                            caller_module=caller_module,
                            caller_class=class_name,
                            import_aliases=import_aliases,
                            module_functions=module_functions,
                            class_methods=class_methods,
                        )
                        edges.add(
                            (
                                caller_module,
                                caller_name,
                                callee_module,
                                callee_name,
                                resolved,
                            )
                        )

        for edge in sorted(
            edges,
            key=lambda item: (
                item[0],
                item[1],
                item[2] or "",
                item[3] or "",
                item[4],
            ),
        ):
            conn.execute(
                "INSERT OR IGNORE INTO call_edges"
                "(caller_module, caller_name, callee_module, callee_name, resolved) "
                "VALUES (?, ?, ?, ?, ?)",
                edge,
            )

        conn.commit()
    finally:
        conn.close()
