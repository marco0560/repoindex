from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _is_public(name: str) -> int:
    return int(not name.startswith("_"))


def _signature_text(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    arg_names = [arg.arg for arg in node.args.args]
    if node.args.vararg is not None:
        arg_names.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg is not None:
        arg_names.append(f"**{node.args.kwarg.arg}")
    return f"{node.name}({', '.join(arg_names)})"


def _module_name_from_path(path: Path, root: Path) -> str:
    rel = path.with_suffix("").relative_to(root)
    parts = list(rel.parts)

    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]

    if parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts)


def _extract_call_names(node: ast.AST) -> list[str]:
    calls: list[str] = []

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue

        func = child.func

        if isinstance(func, ast.Name):
            calls.append(func.id)
        elif isinstance(func, ast.Attribute):
            calls.append(func.attr)

    return calls


def parse_file(path: Path, root: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    module_doc = ast.get_docstring(tree)

    result: dict[str, Any] = {
        "module": {
            "name": _module_name_from_path(path, root),
            "docstring": module_doc,
            "has_docstring": int(module_doc is not None),
        },
        "classes": [],
        "functions": [],
        "imports": [],
    }

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node)
            class_entry: dict[str, Any] = {
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", None),
                "docstring": class_doc,
                "has_docstring": int(class_doc is not None),
                "methods": [],
            }

            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_doc = ast.get_docstring(child)
                    class_entry["methods"].append(
                        {
                            "name": child.name,
                            "lineno": child.lineno,
                            "end_lineno": getattr(child, "end_lineno", None),
                            "signature": _signature_text(child),
                            "docstring": method_doc,
                            "has_docstring": int(method_doc is not None),
                            "is_method": 1,
                            "is_public": _is_public(child.name),
                            "calls": _extract_call_names(child),
                        }
                    )

            result["classes"].append(class_entry)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_doc = ast.get_docstring(node)
            result["functions"].append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", None),
                    "signature": _signature_text(node),
                    "docstring": func_doc,
                    "has_docstring": int(func_doc is not None),
                    "is_method": 0,
                    "is_public": _is_public(node.name),
                    "calls": _extract_call_names(node),
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
                dotted = f"{module}.{alias.name}" if module else alias.name
                result["imports"].append(
                    {
                        "name": dotted,
                        "alias": alias.asname,
                        "lineno": node.lineno,
                    }
                )

    return result
