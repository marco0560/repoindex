"""Tests for NumPy docstring validation helpers."""

from __future__ import annotations

from repoindex.docstring import find_missing_sections, validate_docstring


def test_find_missing_sections_respects_callable_metadata() -> None:
    """
    Ensure required and conditional sections depend on callable metadata.
    """
    doc = """
    Summary.

    Parameters
    ----------
    x : int
        Input value.
    """

    missing = find_missing_sections(
        doc,
        parameters=["x"],
        returns_value=True,
        raises_exception=True,
    )

    assert missing == ["Returns", "Raises"]


def test_validate_docstring_reports_missing_parameter_entry() -> None:
    """
    Ensure all declared parameters must appear in the Parameters section.
    """
    doc = """
    Summary.

    Parameters
    ----------
    x : int
        Input value.

    Returns
    -------
    int
        Result value.
    """

    issues = validate_docstring(
        doc,
        is_public=1,
        parameters=["x", "y"],
        returns_value=True,
    )

    assert ("missing_parameter", "Parameter not documented: y") in issues


def test_validate_docstring_reports_malformed_section_heading() -> None:
    """
    Ensure malformed NumPy section headings are detected.
    """
    doc = """
    Summary.

    Parameters
    x : int
        Input value.
    """

    issues = validate_docstring(
        doc,
        is_public=1,
        parameters=["x"],
    )

    assert (
        "malformed_section",
        "Malformed NumPy section heading: Parameters",
    ) in issues


def test_validate_docstring_requires_raises_only_when_explicit_raise_exists() -> None:
    """
    Ensure missing Raises is only reported for callables with explicit raises.
    """
    doc = """
    Summary.

    Parameters
    ----------
    x : int
        Input value.

    Returns
    -------
    int
        Result value.
    """

    issues = validate_docstring(
        doc,
        is_public=1,
        parameters=["x"],
        returns_value=True,
        raises_exception=True,
    )

    assert ("missing_section", "Missing section: Raises") in issues


def test_validate_docstring_skips_private_missing_docstrings() -> None:
    """
    Ensure private callables are allowed to omit docstrings.
    """
    assert validate_docstring(None, is_public=0) == []
