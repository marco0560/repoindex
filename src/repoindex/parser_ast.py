from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def parse_file(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    module_doc = ast.get_docstring(tree)

    result = {
        "module": {
            "name": path.stem,
            "docstring": module_doc,
            "has_docstring": int(module_doc is not None),
        },
        "classes": [],
        "functions": [],
        "imports": [],
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node)
            result["classes"].append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", None),
                    "docstring": doc,
                    "has_docstring": int(doc is not None),
                }
            )

        elif isinstance(node, ast.FunctionDef):
            doc = ast.get_docstring(node)
            result["functions"].append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", None),
                    "docstring": doc,
                    "has_docstring": int(doc is not None),
                    "is_method": 0,
                    "is_public": int(not node.name.startswith("_")),
                }
            )

        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(
                    {
                        "name": alias.name,
                        "alias": alias.asname,
                        "lineno": node.lineno,
                    }
                )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                result["imports"].append(
                    {
                        "name": f"{module}.{alias.name}",
                        "alias": alias.asname,
                        "lineno": node.lineno,
                    }
                )

    return result
