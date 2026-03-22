from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable, List, Tuple

SymbolRow = Tuple[str, str, str, str, int]
ReferenceRow = Tuple[str, int]
CacheType = dict[Path, tuple[str, list[str], ast.Module]]


def build_prompt(
    root: Path,
    query: str,
    top_matches: List[SymbolRow],
    doc_issues: List[Tuple[str, str]],
    expanded: List[SymbolRow],
    unique_refs: List[ReferenceRow],
    *,
    prompt_symbol_line: Callable[[Path, SymbolRow], str],
    format_enriched_symbol: Callable[[Path, SymbolRow, CacheType], List[str]],
) -> str:
    """
    Deterministic agent prompt builder (full fidelity).

    Notes
    -----
    This is a direct extraction of the original _render_agent_prompt logic.
    """

    cache: dict[Path, tuple[str, list[str], ast.Module]] = {}
    lines: list[str] = []

    lines.append("TASK")
    lines.append("----")
    lines.append(f"Use the repoindex context below to work on query: {query}")
    lines.append("")
    lines.append("MODE")
    lines.append("----")
    lines.append("Deterministic code assistant")
    lines.append("")
    lines.append("RULES")
    lines.append("-----")
    lines.append("- Work only with the symbols and files listed below.")
    lines.append("- Do not invent modules, files, or functions.")
    lines.append("- Prefer PRIMARY TARGETS over supporting symbols.")
    lines.append("- Keep changes minimal and localized.")
    lines.append("- If required information is missing, say so explicitly.")
    lines.append("")
    lines.append("PRIMARY TARGETS")
    lines.append("---------------")

    if not top_matches:
        lines.append("None.")
    else:
        for symbol in top_matches:
            lines.append(prompt_symbol_line(root, symbol))

    lines.append("")
    lines.append("SUPPORTING SYMBOLS")
    lines.append("------------------")

    if not expanded:
        lines.append("None.")
    else:
        for symbol in expanded:
            lines.append(prompt_symbol_line(root, symbol))

    lines.append("")
    lines.append("ENRICHED CONTEXT")
    lines.append("----------------")

    if not top_matches:
        lines.append("None.")
    else:
        for symbol in top_matches[:5]:
            lines.extend(format_enriched_symbol(root, symbol, cache))
            lines.append("")

        if lines[-1] == "":
            lines.pop()

    lines.append("")
    lines.append("CROSS-REFERENCES")
    lines.append("----------------")

    if not unique_refs:
        lines.append("None.")
    else:
        for file_path, lineno in unique_refs:
            try:
                rel_path = str(Path(file_path).relative_to(root))
            except ValueError:
                rel_path = str(file_path)

            lines.append(f"- {rel_path}:{lineno}")

    lines.append("")
    lines.append("DOCSTRING ISSUES")
    lines.append("----------------")

    if not doc_issues:
        lines.append("None.")
    else:
        for issue_type, message in doc_issues:
            lines.append(f"- {issue_type}: {message}")

    lines.append("")
    lines.append("OUTPUT FORMAT")
    lines.append("-------------")
    lines.append("Follow strict patch discipline:")
    lines.append("- FILE path")
    lines.append("- exact OLD block")
    lines.append("- exact NEW block")
    lines.append("- no partial edits")
    lines.append("- no invented code outside visible scope")

    return "\n".join(lines)
