"""JSON analyzer for deterministic structured document indexing.

Responsibilities
----------------
- Recognize JSON document families that expose stable, queryable structure.
- Parse supported JSON files and emit normalized module-level artifacts.
- Keep unsupported JSON files unclaimed so coverage and routing remain explicit.

Design principles
-----------------
The analyzer is intentionally narrow: it indexes only deterministic JSON Schema
documents and avoids inventing symbols for arbitrary JSON blobs.

Architectural role
------------------
This module belongs to the **language analyzer layer** and provides the first
structured JSON analysis path for repoindex.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

from repoindex.models import AnalysisResult, ModuleArtifact


def _sanitize_module_segment(segment: str) -> str:
    """
    Normalize one path segment for JSON module naming.

    Parameters
    ----------
    segment : str
        Raw repository-relative path segment.

    Returns
    -------
    str
        Segment rewritten to avoid ambiguous dotted module names.
    """
    normalized = segment.strip().replace("-", "_").replace(".", "_")
    return normalized.lstrip("_") or "json"


def _module_name_for_path(path: Path, root: Path) -> str:
    """
    Derive the logical module name for one supported JSON file.

    Parameters
    ----------
    path : pathlib.Path
        JSON file being analyzed.
    root : pathlib.Path
        Repository root used for relative naming.

    Returns
    -------
    str
        Dotted module identity derived from the repository-relative path.
    """
    relative = path.relative_to(root)
    parent_segments = [
        _sanitize_module_segment(part) for part in relative.parent.parts if part
    ]
    filename_segment = _sanitize_module_segment(path.stem)
    return ".".join((*parent_segments, filename_segment))


def _module_stable_id(path: Path, root: Path) -> str:
    """
    Build the durable identity for one JSON-backed module.

    Parameters
    ----------
    path : pathlib.Path
        Source path being analyzed.
    root : pathlib.Path
        Repository root used for relative identity derivation.

    Returns
    -------
    str
        Durable JSON module identity.
    """
    return f"json:module:{path.relative_to(root).as_posix()}"


def _load_json_mapping(path: Path) -> dict[str, object]:
    """
    Parse one JSON file and require an object-valued document root.

    Parameters
    ----------
    path : pathlib.Path
        JSON file to parse.

    Returns
    -------
    dict[str, object]
        Parsed top-level JSON object.

    Raises
    ------
    TypeError
        If the top-level JSON value is not an object.
    ValueError
        If the file is not valid JSON.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        msg = f"Unsupported JSON document in {path}: {exc.msg}"
        raise ValueError(msg) from exc

    if not isinstance(payload, dict):
        msg = f"Unsupported JSON document in {path}: top-level value must be an object"
        raise TypeError(msg)

    return cast("dict[str, object]", payload)


def _is_schema_path(path: Path) -> bool:
    """
    Decide whether one source path belongs to the supported schema family.

    Parameters
    ----------
    path : pathlib.Path
        Candidate JSON path to classify.

    Returns
    -------
    bool
        ``True`` when the path lives under a directory named ``schema``.
    """
    return path.parent.name == "schema"


def _is_json_schema_document(payload: dict[str, object]) -> bool:
    """
    Decide whether one parsed JSON object is a JSON Schema document.

    Parameters
    ----------
    payload : dict[str, object]
        Parsed JSON object to classify.

    Returns
    -------
    bool
        ``True`` when the document exposes deterministic JSON Schema markers.
    """
    schema_uri = payload.get("$schema")
    if isinstance(schema_uri, str) and schema_uri.strip():
        return True
    return "$defs" in payload or "definitions" in payload


def _schema_docstring(payload: dict[str, object]) -> str:
    """
    Build the module summary used for one JSON Schema document.

    Parameters
    ----------
    payload : dict[str, object]
        Parsed JSON Schema document.

    Returns
    -------
    str
        Concise module summary for indexing and explain output.
    """
    title = payload.get("title")
    description = payload.get("description")

    if isinstance(title, str) and title.strip():
        summary = f"JSON Schema: {title.strip()}."
    else:
        summary = "JSON Schema document."

    if isinstance(description, str) and description.strip():
        return f"{summary} {description.strip()}"
    return summary


class JsonAnalyzer:
    """
    Concrete JSON analyzer for deterministic structured documents.

    Parameters
    ----------
    None

    Notes
    -----
    The current scope intentionally covers JSON Schema documents only. Generic
    configuration blobs remain unclaimed until a deterministic family contract
    is defined for them.
    """

    name = "json"
    version = "1"
    discovery_globs: tuple[str, ...] = ("**/schema/*.json",)

    def supports_path(self, path: Path) -> bool:
        """
        Decide whether the analyzer accepts a JSON source path.

        Parameters
        ----------
        path : pathlib.Path
            Candidate repository file.

        Returns
        -------
        bool
            ``True`` when the file is a supported JSON Schema document.
        """
        if path.suffix != ".json" or not _is_schema_path(path):
            return False

        try:
            payload = _load_json_mapping(path)
        except (TypeError, ValueError):
            return False

        return _is_json_schema_document(payload)

    def analyze_file(self, path: Path, root: Path) -> AnalysisResult:
        """
        Analyze one JSON Schema file into normalized artifacts.

        Parameters
        ----------
        path : pathlib.Path
            JSON file to analyze.
        root : pathlib.Path
            Repository root used for module naming.

        Returns
        -------
        repoindex.models.AnalysisResult
            Normalized analysis result for the JSON Schema file.

        Raises
        ------
        TypeError
            If the parsed JSON document is not object-valued.
        ValueError
            If ``path`` does not hold a supported JSON Schema document.
        """
        payload = _load_json_mapping(path)
        if not _is_schema_path(path) or not _is_json_schema_document(payload):
            msg = f"Unsupported JSON document in {path}: no recognized schema markers"
            raise ValueError(msg)

        module_docstring = _schema_docstring(payload)
        return AnalysisResult(
            source_path=path,
            module=ModuleArtifact(
                name=_module_name_for_path(path, root),
                stable_id=_module_stable_id(path, root),
                docstring=module_docstring,
                has_docstring=1,
            ),
            classes=(),
            functions=(),
            declarations=(),
            imports=(),
        )
