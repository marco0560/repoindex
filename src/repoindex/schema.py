from __future__ import annotations

SCHEMA_VERSION = 2

DDL = [
    """
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY,
        path TEXT UNIQUE NOT NULL,
        hash TEXT NOT NULL,
        mtime REAL NOT NULL,
        size INTEGER NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS modules (
        id INTEGER PRIMARY KEY,
        file_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        docstring TEXT,
        has_docstring INTEGER NOT NULL,
        FOREIGN KEY(file_id) REFERENCES files(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY,
        module_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        lineno INTEGER NOT NULL,
        end_lineno INTEGER,
        docstring TEXT,
        has_docstring INTEGER NOT NULL,
        FOREIGN KEY(module_id) REFERENCES modules(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS functions (
        id INTEGER PRIMARY KEY,
        module_id INTEGER NOT NULL,
        class_id INTEGER,
        name TEXT NOT NULL,
        lineno INTEGER NOT NULL,
        end_lineno INTEGER,
        signature TEXT,
        docstring TEXT,
        has_docstring INTEGER NOT NULL,
        is_method INTEGER NOT NULL,
        is_public INTEGER NOT NULL,
        FOREIGN KEY(module_id) REFERENCES modules(id),
        FOREIGN KEY(class_id) REFERENCES classes(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY,
        module_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        alias TEXT,
        lineno INTEGER NOT NULL,
        FOREIGN KEY(module_id) REFERENCES modules(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS docstring_issues (
        id INTEGER PRIMARY KEY,
        function_id INTEGER,
        class_id INTEGER,
        module_id INTEGER,
        issue_type TEXT NOT NULL,
        message TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS symbol_index (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        module_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        lineno INTEGER NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS call_edges (
        id INTEGER PRIMARY KEY,
        caller_file_path TEXT NOT NULL,
        caller_lineno INTEGER NOT NULL,
        caller_name TEXT NOT NULL,
        callee_name TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS embeddings (
        id INTEGER PRIMARY KEY,
        object_type TEXT NOT NULL,
        object_id INTEGER NOT NULL,
        vector BLOB NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_symbol_name ON symbol_index(name);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_call_edges_caller
    ON call_edges(caller_file_path, caller_lineno);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_call_edges_callee
    ON call_edges(callee_name);
    """,
]
