"""Index repository symbols and docstring diagnostics into SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from repoindex.docstring import validate_docstring
from repoindex.parser_ast import parse_file
from repoindex.scanner import file_metadata, iter_project_files
from repoindex.semantic.embeddings import (
    EmbeddingBackendSpec,
    embed_text,
    get_embedding_backend,
    serialize_vector,
)
from repoindex.storage import get_db_path

CallRecord = dict[str, str | int]
ReferenceRecord = dict[str, str | int]
ParsedFile = tuple[Path, dict[str, object], dict[str, object]]


@dataclass(frozen=True)
class IndexDecision:
    """
    Deterministic per-file indexing decision.

    Parameters
    ----------
    path : str
        Absolute file path considered by the indexer.
    action : str
        Decision category such as ``indexed``, ``reused``, or ``deleted``.
    reason : str
        Stable explanation for the decision.
    """

    path: str
    action: str
    reason: str


@dataclass(frozen=True)
class IndexReport:
    """
    Summary of one indexing run.

    Parameters
    ----------
    indexed : int
        Number of files reparsed and reindexed.
    reused : int
        Number of files reused without reparsing.
    deleted : int
        Number of deleted files removed from the index.
    embeddings_recomputed : int
        Number of embeddings written during the run.
    embeddings_reused : int
        Number of existing embeddings preserved for unchanged files.
    decisions : list[IndexDecision]
        Deterministic per-file decisions for explain mode.
    """

    indexed: int
    reused: int
    deleted: int
    embeddings_recomputed: int
    embeddings_reused: int
    decisions: list[IndexDecision]


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
    conn.execute("DELETE FROM callable_refs")
    conn.execute("DELETE FROM call_records")
    conn.execute("DELETE FROM callable_ref_records")
    conn.execute("DELETE FROM embeddings")
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

        methods = class_methods.get((caller_module, base), set())
        if target in methods:
            candidates.add((caller_module, _qualified_callable_name(target, base)))

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


def _embedding_text(
    *,
    module_name: str,
    symbol_name: str,
    symbol_type: str,
    signature: str | None = None,
    docstring: str | None = None,
) -> str:
    """
    Build the deterministic text payload embedded for one symbol.

    Parameters
    ----------
    module_name : str
        Dotted module name that owns the symbol.
    symbol_name : str
        Logical symbol name.
    symbol_type : str
        Indexed symbol type.
    signature : str | None, optional
        Callable signature when present.
    docstring : str | None, optional
        Symbol docstring when present.

    Returns
    -------
    str
        Joined text payload used for embedding generation.
    """
    parts = [symbol_type, module_name, symbol_name]
    if signature:
        parts.append(signature)
    if docstring:
        parts.append(docstring)
    return "\n".join(parts)


def _placeholders(values: list[int]) -> str:
    """
    Build a positional placeholder string for SQL ``IN`` clauses.

    Parameters
    ----------
    values : list[int]
        Integer values that will populate the clause.

    Returns
    -------
    str
        Comma-separated ``?`` placeholders sized to ``values``.
    """
    return ",".join("?" for _ in values)


def _delete_indexed_file_data(conn: sqlite3.Connection, file_path: str) -> None:
    """
    Remove all indexed data owned by one file.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    file_path : str
        Absolute file path whose indexed rows should be removed.

    Returns
    -------
    None
        The rows are deleted in place on ``conn``.
    """
    module_ids = [
        int(row[0])
        for row in conn.execute(
            """
            SELECT m.id
            FROM modules m
            JOIN files f
              ON m.file_id = f.id
            WHERE f.path = ?
            """,
            (file_path,),
        ).fetchall()
    ]
    class_ids: list[int] = []
    function_ids: list[int] = []
    symbol_ids = [
        int(row[0])
        for row in conn.execute(
            "SELECT id FROM symbol_index WHERE file_path = ?",
            (file_path,),
        ).fetchall()
    ]

    if module_ids:
        class_ids = [
            int(row[0])
            for row in conn.execute(
                "SELECT id FROM classes WHERE module_id IN "
                f"({_placeholders(module_ids)})",
                tuple(module_ids),
            ).fetchall()
        ]
        function_ids = [
            int(row[0])
            for row in conn.execute(
                "SELECT id FROM functions WHERE module_id IN "
                f"({_placeholders(module_ids)})",
                tuple(module_ids),
            ).fetchall()
        ]

    if symbol_ids:
        conn.execute(
            f"DELETE FROM embeddings WHERE object_type = 'symbol' "
            f"AND object_id IN ({_placeholders(symbol_ids)})",
            tuple(symbol_ids),
        )

    if function_ids:
        conn.execute(
            "DELETE FROM docstring_issues WHERE function_id IN "
            f"({_placeholders(function_ids)})",
            tuple(function_ids),
        )
    if class_ids:
        conn.execute(
            "DELETE FROM docstring_issues WHERE class_id IN "
            f"({_placeholders(class_ids)})",
            tuple(class_ids),
        )
    if module_ids:
        conn.execute(
            "DELETE FROM docstring_issues WHERE module_id IN "
            f"({_placeholders(module_ids)})",
            tuple(module_ids),
        )
        conn.execute(
            f"DELETE FROM imports WHERE module_id IN ({_placeholders(module_ids)})",
            tuple(module_ids),
        )
        conn.execute(
            f"DELETE FROM functions WHERE module_id IN ({_placeholders(module_ids)})",
            tuple(module_ids),
        )
        conn.execute(
            f"DELETE FROM classes WHERE module_id IN ({_placeholders(module_ids)})",
            tuple(module_ids),
        )
        conn.execute(
            f"DELETE FROM modules WHERE id IN ({_placeholders(module_ids)})",
            tuple(module_ids),
        )

    conn.execute("DELETE FROM symbol_index WHERE file_path = ?", (file_path,))
    conn.execute("DELETE FROM call_records WHERE file_path = ?", (file_path,))
    conn.execute("DELETE FROM callable_ref_records WHERE file_path = ?", (file_path,))
    conn.execute("DELETE FROM files WHERE path = ?", (file_path,))


def _current_embedding_state_matches(
    conn: sqlite3.Connection,
    backend: EmbeddingBackendSpec,
) -> bool:
    """
    Check whether stored embeddings already match the active backend state.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    backend : EmbeddingBackendSpec
        Active embedding backend metadata.

    Returns
    -------
    bool
        ``True`` when all stored embeddings use the active backend and version.
    """
    rows = conn.execute(
        "SELECT DISTINCT backend, version FROM embeddings ORDER BY backend, version"
    ).fetchall()
    if not rows:
        return True
    return rows == [(backend.name, backend.version)]


def _load_existing_file_hashes(conn: sqlite3.Connection) -> dict[str, str]:
    """
    Load indexed file hashes keyed by path.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[str, str]
        Indexed file hashes keyed by absolute path.
    """
    rows = conn.execute("SELECT path, hash FROM files ORDER BY path").fetchall()
    return {str(path): str(file_hash) for path, file_hash in rows}


def _count_reused_embeddings(
    conn: sqlite3.Connection,
    reused_paths: list[str],
) -> int:
    """
    Count preserved embedding rows for unchanged files.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    reused_paths : list[str]
        Absolute file paths reused without reparsing.

    Returns
    -------
    int
        Number of embedding rows preserved for the reused files.
    """
    if not reused_paths:
        return 0

    placeholders = ",".join("?" for _ in reused_paths)
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM embeddings e
        JOIN symbol_index s
          ON e.object_type = 'symbol'
         AND e.object_id = s.id
        WHERE s.file_path IN ({placeholders})
        """,
        tuple(reused_paths),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _load_module_functions(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """
    Load known top-level functions from indexed structural tables.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[str, set[str]]
        Top-level function names keyed by module name.
    """
    rows = conn.execute("""
        SELECT m.name, f.name
        FROM functions f
        JOIN modules m
          ON f.module_id = m.id
        WHERE f.class_id IS NULL
        ORDER BY m.name, f.name
        """).fetchall()
    module_functions: dict[str, set[str]] = {}
    for module_name, function_name in rows:
        module_functions.setdefault(str(module_name), set()).add(str(function_name))
    return module_functions


def _load_class_methods(conn: sqlite3.Connection) -> dict[tuple[str, str], set[str]]:
    """
    Load known methods from indexed structural tables.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[tuple[str, str], set[str]]
        Method names keyed by ``(module_name, class_name)``.
    """
    rows = conn.execute("""
        SELECT m.name, c.name, f.name
        FROM functions f
        JOIN classes c
          ON f.class_id = c.id
        JOIN modules m
          ON f.module_id = m.id
        ORDER BY m.name, c.name, f.name
        """).fetchall()
    class_methods: dict[tuple[str, str], set[str]] = {}
    for module_name, class_name, method_name in rows:
        key = (str(module_name), str(class_name))
        class_methods.setdefault(key, set()).add(str(method_name))
    return class_methods


def _load_import_aliases(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """
    Load import alias maps for indexed modules.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict[str, dict[str, str]]
        Alias maps keyed by owning module name.
    """
    rows = conn.execute("""
        SELECT m.name, i.name, i.alias
        FROM imports i
        JOIN modules m
          ON i.module_id = m.id
        ORDER BY m.name, i.lineno, i.name, COALESCE(i.alias, '')
        """).fetchall()
    imports_by_module: dict[str, list[dict[str, object]]] = {}
    for module_name, import_name, alias in rows:
        imports_by_module.setdefault(str(module_name), []).append(
            {
                "name": str(import_name),
                "alias": None if alias is None else str(alias),
            }
        )

    return {
        module_name: _import_alias_map(imports)
        for module_name, imports in imports_by_module.items()
    }


def _caller_class_from_owner(owner_name: str) -> str | None:
    """
    Derive the owning class name from a logical callable owner.

    Parameters
    ----------
    owner_name : str
        Logical callable owner name.

    Returns
    -------
    str | None
        Owning class name for methods, or ``None`` for top-level functions.
    """
    if "." not in owner_name:
        return None
    class_name, _method_name = owner_name.rsplit(".", 1)
    return class_name


def _rebuild_graph_indexes(conn: sqlite3.Connection) -> None:
    """
    Rebuild derived call and callable-reference edges from stored raw records.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    None
        The derived edge tables are replaced in place.
    """
    module_functions = _load_module_functions(conn)
    class_methods = _load_class_methods(conn)
    import_aliases_by_module = _load_import_aliases(conn)

    conn.execute("DELETE FROM call_edges")
    conn.execute("DELETE FROM callable_refs")

    edges: set[tuple[str, str, str | None, str | None, int]] = set()
    refs: set[tuple[str, str, str | None, str | None, int]] = set()

    call_rows = conn.execute("""
        SELECT owner_module, owner_name, kind, base, target, lineno, col_offset
        FROM call_records
        ORDER BY owner_module, owner_name, lineno, col_offset, kind, base, target
        """).fetchall()
    for owner_module, owner_name, kind, base, target, _lineno, _col_offset in call_rows:
        record = cast(
            CallRecord,
            {
                "kind": str(kind),
                "base": str(base),
                "target": str(target),
            },
        )
        caller_module = str(owner_module)
        caller_name = str(owner_name)
        callee_module, callee_name, resolved = _resolve_call_record(
            record,
            caller_module=caller_module,
            caller_class=_caller_class_from_owner(caller_name),
            import_aliases=import_aliases_by_module.get(caller_module, {}),
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

    ref_rows = conn.execute("""
        SELECT owner_module, owner_name, kind, base, target, lineno, col_offset
        FROM callable_ref_records
        ORDER BY
            owner_module,
            owner_name,
            lineno,
            col_offset,
            kind,
            base,
            target
        """).fetchall()
    for owner_module, owner_name, kind, base, target, _lineno, _col_offset in ref_rows:
        record = cast(
            CallRecord,
            {
                "kind": str(kind),
                "base": str(base),
                "target": str(target),
            },
        )
        caller_module = str(owner_module)
        caller_name = str(owner_name)
        target_module, target_name, resolved = _resolve_call_record(
            record,
            caller_module=caller_module,
            caller_class=_caller_class_from_owner(caller_name),
            import_aliases=import_aliases_by_module.get(caller_module, {}),
            module_functions=module_functions,
            class_methods=class_methods,
        )
        refs.add(
            (
                caller_module,
                caller_name,
                target_module,
                target_name,
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

    for ref_row in sorted(
        refs,
        key=lambda item: (
            item[0],
            item[1],
            item[2] or "",
            item[3] or "",
            item[4],
        ),
    ):
        conn.execute(
            "INSERT OR IGNORE INTO callable_refs"
            "(owner_module, owner_name, target_module, target_name, resolved) "
            "VALUES (?, ?, ?, ?, ?)",
            ref_row,
        )


def _record_tuple(
    file_path: str,
    owner_module: str,
    owner_name: str,
    record: dict[str, str | int],
) -> tuple[str, str, str, str, str, str, int, int]:
    """
    Normalize one raw call-style record for SQLite persistence.

    Parameters
    ----------
    file_path : str
        Absolute owner file path.
    owner_module : str
        Owning module name.
    owner_name : str
        Logical owner name.
    record : dict[str, str | int]
        Parsed call or callable-reference record.

    Returns
    -------
    tuple[str, str, str, str, str, str, int, int]
        Normalized SQLite row values.
    """
    return (
        file_path,
        owner_module,
        owner_name,
        str(record.get("kind", "unresolved")),
        str(record.get("base", "")),
        str(record.get("target", "")),
        int(record.get("lineno", 0)),
        int(record.get("col_offset", 0)),
    )


def _store_parsed_file(
    conn: sqlite3.Connection,
    meta: dict[str, object],
    parsed: dict[str, object],
    *,
    backend: EmbeddingBackendSpec,
) -> int:
    """
    Persist one parsed file snapshot into the index.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    meta : dict[str, object]
        Stable file metadata for the parsed file.
    parsed : dict[str, object]
        Parsed AST output for the file.
    backend : EmbeddingBackendSpec
        Active embedding backend metadata.

    Returns
    -------
    int
        Number of embeddings recomputed for the file.
    """
    embedding_rows: list[tuple[str, int, str]] = []
    call_rows: list[tuple[str, str, str, str, str, str, int, int]] = []
    ref_rows: list[tuple[str, str, str, str, str, str, str, int, int]] = []

    module = cast(dict[str, object], parsed["module"])
    classes = cast(list[dict[str, object]], parsed["classes"])
    functions = cast(list[dict[str, object]], parsed["functions"])
    imports = cast(list[dict[str, object]], parsed["imports"])

    file_path = str(meta["path"])
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
        "(name, type, module_name, file_path, lineno) VALUES (?, ?, ?, ?, ?)",
        (module_name, "module", module_name, file_path, 1),
    )
    symbol_row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    embedding_rows.append(
        (
            "symbol",
            symbol_row_id,
            _embedding_text(
                module_name=module_name,
                symbol_name=module_name,
                symbol_type="module",
                docstring=cast(str | None, module["docstring"]),
            ),
        )
    )

    for issue_type, message in validate_docstring(
        cast(str | None, module["docstring"]),
        is_public=1,
    ):
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
            "(name, type, module_name, file_path, lineno) VALUES (?, ?, ?, ?, ?)",
            (
                cls["name"],
                "class",
                module_name,
                file_path,
                cls["lineno"],
            ),
        )
        symbol_row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        embedding_rows.append(
            (
                "symbol",
                symbol_row_id,
                _embedding_text(
                    module_name=module_name,
                    symbol_name=str(cls["name"]),
                    symbol_type="class",
                    docstring=cast(str | None, cls["docstring"]),
                ),
            )
        )

        for issue_type, message in validate_docstring(
            cast(str | None, cls["docstring"]),
            is_public=1,
        ):
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
            logical_name = _qualified_callable_name(
                str(method["name"]),
                str(cls["name"]),
            )
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
                "(name, type, module_name, file_path, lineno) VALUES (?, ?, ?, ?, ?)",
                (
                    method["name"],
                    "method",
                    module_name,
                    file_path,
                    method["lineno"],
                ),
            )
            symbol_row_id = int(
                conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            )
            embedding_rows.append(
                (
                    "symbol",
                    symbol_row_id,
                    _embedding_text(
                        module_name=module_name,
                        symbol_name=logical_name,
                        symbol_type="method",
                        signature=cast(str | None, method["signature"]),
                        docstring=cast(str | None, method["docstring"]),
                    ),
                )
            )

            for issue_type, message in validate_docstring(
                cast(str | None, method["docstring"]),
                cast(int, method["is_public"]),
                parameters=cast(list[str], method["parameters"]),
                require_callable_sections=True,
                yields_value=bool(method["yields_value"]),
                returns_value=bool(method["returns_value"]),
                raises_exception=bool(method["raises"]),
            ):
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

            for call in cast(list[CallRecord], method["calls"]):
                call_rows.append(
                    _record_tuple(file_path, module_name, logical_name, call)
                )
            for ref in cast(list[ReferenceRecord], method["callable_refs"]):
                ref_rows.append(
                    (
                        file_path,
                        module_name,
                        logical_name,
                        str(ref.get("kind", "unresolved")),
                        str(ref.get("ref_kind", "")),
                        str(ref.get("base", "")),
                        str(ref.get("target", "")),
                        int(ref.get("lineno", 0)),
                        int(ref.get("col_offset", 0)),
                    )
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
            "(name, type, module_name, file_path, lineno) VALUES (?, ?, ?, ?, ?)",
            (
                fn["name"],
                "function",
                module_name,
                file_path,
                fn["lineno"],
            ),
        )
        symbol_row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        embedding_rows.append(
            (
                "symbol",
                symbol_row_id,
                _embedding_text(
                    module_name=module_name,
                    symbol_name=str(fn["name"]),
                    symbol_type="function",
                    signature=cast(str | None, fn["signature"]),
                    docstring=cast(str | None, fn["docstring"]),
                ),
            )
        )

        for issue_type, message in validate_docstring(
            cast(str | None, fn["docstring"]),
            cast(int, fn["is_public"]),
            parameters=cast(list[str], fn["parameters"]),
            require_callable_sections=True,
            yields_value=bool(fn["yields_value"]),
            returns_value=bool(fn["returns_value"]),
            raises_exception=bool(fn["raises"]),
        ):
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

        for call in cast(list[CallRecord], fn["calls"]):
            call_rows.append(
                _record_tuple(file_path, module_name, str(fn["name"]), call)
            )
        for ref in cast(list[ReferenceRecord], fn["callable_refs"]):
            ref_rows.append(
                (
                    file_path,
                    module_name,
                    str(fn["name"]),
                    str(ref.get("kind", "unresolved")),
                    str(ref.get("ref_kind", "")),
                    str(ref.get("base", "")),
                    str(ref.get("target", "")),
                    int(ref.get("lineno", 0)),
                    int(ref.get("col_offset", 0)),
                )
            )

    for imp in imports:
        conn.execute(
            "INSERT INTO imports(module_id, name, alias, lineno) VALUES (?, ?, ?, ?)",
            (
                module_id,
                imp["name"],
                imp["alias"],
                imp["lineno"],
            ),
        )

    for row in sorted(call_rows):
        conn.execute(
            "INSERT INTO call_records"
            "(file_path, owner_module, owner_name, kind, base, target, "
            "lineno, col_offset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )

    for ref_row in sorted(ref_rows):
        conn.execute(
            "INSERT INTO callable_ref_records"
            "(file_path, owner_module, owner_name, kind, ref_kind, base, "
            "target, lineno, col_offset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ref_row,
        )

    for object_type, object_id, text in sorted(
        embedding_rows,
        key=lambda item: item[:2],
    ):
        conn.execute(
            "INSERT INTO embeddings"
            "(object_type, object_id, backend, version, dim, vector) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                object_type,
                object_id,
                backend.name,
                backend.version,
                backend.dim,
                serialize_vector(embed_text(text)),
            ),
        )

    return len(embedding_rows)


def index_repo(
    root: Path,
    *,
    full: bool = False,
) -> IndexReport:
    """
    Incrementally scan repository files and update the SQLite index.

    Parameters
    ----------
    root : pathlib.Path
        Repository root whose tracked Python files should be indexed.
    full : bool, optional
        When ``True``, force a full rebuild instead of reusing unchanged files.

    Returns
    -------
    IndexReport
        Deterministic summary of the indexing run.
    """
    db_path = get_db_path(root)
    conn = sqlite3.connect(db_path)
    backend = get_embedding_backend()

    try:
        current_metadata = {
            str(path): file_metadata(path) for path in sorted(iter_project_files(root))
        }
        current_paths = sorted(current_metadata)
        existing_hashes = _load_existing_file_hashes(conn)
        existing_paths = sorted(existing_hashes)
        backend_matches = _current_embedding_state_matches(conn, backend)

        deleted_paths = [
            path for path in existing_paths if path not in current_metadata
        ]
        reused_paths: list[str] = []
        indexed_paths: list[str] = []
        decisions: list[IndexDecision] = []

        if full:
            indexed_paths = list(current_paths)
            for path in current_paths:
                decisions.append(
                    IndexDecision(path, "indexed", "full rebuild requested")
                )
        else:
            for path in current_paths:
                existing_hash = existing_hashes.get(path)
                current_hash = str(current_metadata[path]["hash"])
                if existing_hash is None:
                    indexed_paths.append(path)
                    decisions.append(IndexDecision(path, "indexed", "new file"))
                elif existing_hash != current_hash:
                    indexed_paths.append(path)
                    decisions.append(
                        IndexDecision(path, "indexed", "file content changed")
                    )
                elif not backend_matches:
                    indexed_paths.append(path)
                    decisions.append(
                        IndexDecision(
                            path,
                            "indexed",
                            "embedding backend or version changed",
                        )
                    )
                else:
                    reused_paths.append(path)
                    decisions.append(
                        IndexDecision(path, "reused", "file hash unchanged")
                    )

        for path in deleted_paths:
            decisions.append(IndexDecision(path, "deleted", "file removed"))

        if full:
            _clear_index_tables(conn)
        else:
            for path in sorted(set(indexed_paths) | set(deleted_paths)):
                _delete_indexed_file_data(conn, path)

        embeddings_reused = 0 if full else _count_reused_embeddings(conn, reused_paths)

        parsed_files: list[ParsedFile] = []
        for path in indexed_paths:
            path_obj = Path(path)
            parsed_files.append(
                (path_obj, current_metadata[path], parse_file(path_obj, root))
            )

        embeddings_recomputed = 0
        for _path, meta, parsed in parsed_files:
            embeddings_recomputed += _store_parsed_file(
                conn,
                meta,
                parsed,
                backend=backend,
            )

        _rebuild_graph_indexes(conn)
        conn.commit()

        decisions.sort(
            key=lambda decision: (
                decision.action,
                decision.path,
                decision.reason,
            )
        )

        return IndexReport(
            indexed=len(indexed_paths),
            reused=len(reused_paths),
            deleted=len(deleted_paths),
            embeddings_recomputed=embeddings_recomputed,
            embeddings_reused=embeddings_reused,
            decisions=decisions,
        )
    finally:
        conn.close()
