"""Docstring validation helpers used during indexing."""

from __future__ import annotations

import inspect
import re
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
KNOWN_SECTIONS = REQUIRED_SECTIONS + OPTIONAL_SECTIONS
SECTION_HEADING_RE = re.compile(r"^[A-Z][A-Za-z ]+$")
PARAMETER_LINE_RE = re.compile(r"^([*]{0,2}[A-Za-z_][A-Za-z0-9_]*)\s*:")


def _iter_lines(doc: str) -> list[str]:
    """
    Split a docstring into normalized lines.

    Parameters
    ----------
    doc : str
        Docstring text to inspect.

    Returns
    -------
    list[str]
        Normalized docstring lines.
    """
    return [line.rstrip() for line in inspect.cleandoc(doc).splitlines()]


def _section_map(doc: str) -> dict[str, tuple[int, int]]:
    """
    Locate NumPy-style section bodies in a docstring.

    Parameters
    ----------
    doc : str
        Docstring text to inspect.

    Returns
    -------
    dict[str, tuple[int, int]]
        Mapping from section name to inclusive start and exclusive end line
        indices for that section body.
    """
    lines = _iter_lines(doc)
    sections: dict[str, tuple[int, int]] = {}
    headers: list[tuple[str, int]] = []

    for index, line in enumerate(lines[:-1]):
        if line not in KNOWN_SECTIONS:
            continue
        underline = lines[index + 1].strip()
        if underline and set(underline) == {"-"} and len(underline) >= len(line):
            headers.append((line, index))

    for header_index, (name, start) in enumerate(headers):
        body_start = start + 2
        body_end = len(lines)
        if header_index + 1 < len(headers):
            body_end = headers[header_index + 1][1]
        sections[name] = (body_start, body_end)

    return sections


def _malformed_sections(doc: str) -> list[str]:
    """
    Detect known section headings that are not in NumPy format.

    Parameters
    ----------
    doc : str
        Docstring text to inspect.

    Returns
    -------
    list[str]
        Known section names that appear without a valid underline.
    """
    lines = _iter_lines(doc)
    valid = set(_section_map(doc))
    malformed: list[str] = []

    for index, line in enumerate(lines):
        if line not in KNOWN_SECTIONS or line in valid:
            continue
        if not SECTION_HEADING_RE.match(line):
            continue
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if not next_line or set(next_line) != {"-"}:
            malformed.append(line)

    return malformed


def _parameter_section_names(doc: str) -> set[str]:
    """
    Extract documented parameter names from the ``Parameters`` section.

    Parameters
    ----------
    doc : str
        Docstring text to inspect.

    Returns
    -------
    set[str]
        Parameter names documented in the ``Parameters`` section.
    """
    sections = _section_map(doc)
    if "Parameters" not in sections:
        return set()

    lines = _iter_lines(doc)
    start, end = sections["Parameters"]
    names: set[str] = set()

    for line in lines[start:end]:
        match = PARAMETER_LINE_RE.match(line.strip())
        if match is None:
            continue
        names.add(match.group(1).lstrip("*"))

    return names


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
    sections = _section_map(doc)
    return "Parameters" in sections or "Returns" in sections


def find_missing_sections(
    doc: str,
    *,
    parameters: list[str] | None = None,
    returns_value: bool = False,
    raises_exception: bool = False,
) -> List[str]:
    """
    List required or conditional NumPy sections missing from a docstring.

    Parameters
    ----------
    doc : str
        Docstring text to inspect.
    parameters : list[str] | None, optional
        Logical parameter names declared by the callable.
    returns_value : bool, optional
        Whether the callable explicitly returns a value.
    raises_exception : bool, optional
        Whether the callable explicitly raises an exception.

    Returns
    -------
    list[str]
        Missing section names implied by the supplied callable metadata.
    """
    sections = _section_map(doc)
    missing: List[str] = []

    if parameters and "Parameters" not in sections:
        missing.append("Parameters")

    if returns_value and "Returns" not in sections:
        missing.append("Returns")

    if raises_exception and "Raises" not in sections:
        missing.append("Raises")

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
    return "Raises" in _section_map(doc)


def validate_docstring(
    doc: str | None,
    is_public: int,
    *,
    parameters: list[str] | None = None,
    returns_value: bool = False,
    raises_exception: bool = False,
) -> list[tuple[str, str]]:
    """
    Validate a docstring against the project's minimal style rules.

    Parameters
    ----------
    doc : str | None
        Docstring text to validate.
    is_public : int
        Public visibility flag, where ``1`` means public and ``0`` means
        private.
    parameters : list[str] | None, optional
        Logical parameter names declared by the callable.
    returns_value : bool, optional
        Whether the callable explicitly returns a value.
    raises_exception : bool, optional
        Whether the callable explicitly raises an exception.

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

    sections = _section_map(doc)

    if not is_numpy_style(doc):
        issues.append(("non_numpy", "Docstring not in NumPy style"))

    for section in _malformed_sections(doc):
        issues.append(
            ("malformed_section", f"Malformed NumPy section heading: {section}")
        )

    for section in find_missing_sections(
        doc,
        parameters=parameters,
        returns_value=returns_value,
        raises_exception=raises_exception,
    ):
        issues.append(("missing_section", f"Missing section: {section}"))

    documented_parameters = _parameter_section_names(doc)
    for parameter in parameters or []:
        if "Parameters" not in sections:
            break
        if parameter not in documented_parameters:
            issues.append(
                (
                    "missing_parameter",
                    f"Parameter not documented: {parameter}",
                )
            )

    return issues
