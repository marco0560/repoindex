"""Docstring validation helpers used during indexing."""

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
    """
    Check whether a docstring contains basic NumPy-style sections.

    Parameters
    ----------
    doc : str
        Docstring text to inspect.

    Returns
    -------
    bool
        ``True`` when the docstring contains at least one core NumPy section.
    """
    return "Parameters" in doc or "Returns" in doc


def find_missing_sections(doc: str) -> List[str]:
    """
    List required NumPy sections missing from a docstring.

    Parameters
    ----------
    doc : str
        Docstring text to inspect.

    Returns
    -------
    list[str]
        Required section names that are not present.
    """
    missing: List[str] = []

    for section in REQUIRED_SECTIONS:
        if section not in doc:
            missing.append(section)

    return missing


def has_raises_section(doc: str) -> bool:
    """
    Check whether a docstring declares a ``Raises`` section.

    Parameters
    ----------
    doc : str
        Docstring text to inspect.

    Returns
    -------
    bool
        ``True`` when the docstring contains a ``Raises`` heading.
    """
    return "Raises" in doc


def validate_docstring(doc: str | None, is_public: int) -> list[tuple[str, str]]:
    """
    Validate a docstring against the project's minimal style rules.

    Parameters
    ----------
    doc : str | None
        Docstring text to validate.
    is_public : int
        Public visibility flag, where ``1`` means public and ``0`` means
        private.

    Returns
    -------
    list[tuple[str, str]]
        Validation issues as ``(issue_type, message)`` tuples.
    """
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
