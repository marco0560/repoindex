"""Regression tests for context rendering quality."""

from __future__ import annotations

import ast
from pathlib import Path

from repoindex.query.context import _append_main_context_sections, _snippet_from_node


def test_snippet_from_node_removes_docstring_and_collapses_blank_lines() -> None:
    """
    Ensure extracted snippets remain compact after docstring removal.
    """
    source = (
        "def demo(x):\n"
        '    """Example docstring."""\n'
        "\n"
        "    value = x + 1\n"
        "\n"
        "    return value\n"
    )
    tree = ast.parse(source)
    node = tree.body[0]

    snippet = _snippet_from_node(node, source.splitlines())

    assert snippet == [
        "def demo(x):",
        "",
        "    value = x + 1",
        "",
        "    return value",
    ]


def test_append_main_context_sections_separates_enriched_blocks(tmp_path: Path) -> None:
    """
    Ensure plain-text context keeps enriched symbol blocks visually separated.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary repository root used to create fixture files.
    """
    first = tmp_path / "alpha.py"
    second = tmp_path / "beta.py"

    first.write_text(
        "def alpha():\n"
        '    """Alpha docstring."""\n'
        "    return 1\n",
        encoding="utf-8",
    )
    second.write_text(
        "def beta():\n"
        '    """Beta docstring."""\n'
        "    return 2\n",
        encoding="utf-8",
    )

    top_matches = [
        ("function", "alpha", "alpha", "alpha.py", 1),
        ("function", "beta", "beta", "beta.py", 1),
    ]

    lines: list[str] = []
    _append_main_context_sections(lines, tmp_path, top_matches, [], [], [])

    rendered = "\n".join(lines)

    assert "function alpha()" in rendered
    assert "function beta()" in rendered
    assert "    Alpha docstring.\n\nfunction beta()" in rendered
