from __future__ import annotations

from typing import List

REQUIRED_SECTIONS = [
    "Parameters",
    "Returns",
]

OPTIONAL_SECTIONS = [
    "Raises",
    "Notes",
    "Examples",
]


def is_numpy_style(doc: str) -> bool:
    return "Parameters" in doc or "Returns" in doc


def find_missing_sections(doc: str) -> List[str]:
    missing: List[str] = []

    for section in REQUIRED_SECTIONS:
        if section not in doc:
            missing.append(section)

    return missing


def has_raises_section(doc: str) -> bool:
    return "Raises" in doc


def validate_docstring(doc: str | None, is_public: int) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []

    if not doc:
        if not is_public:
            return []
        return [("missing", "Missing docstring")]

    if not is_numpy_style(doc):
        issues.append(("non_numpy", "Docstring not in NumPy style"))

    for section in find_missing_sections(doc):
        issues.append(("missing_section", f"Missing section: {section}"))

    return issues
