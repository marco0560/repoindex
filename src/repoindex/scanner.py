"""Filesystem and Git-backed file discovery helpers for indexing."""

from __future__ import annotations

import fnmatch
import hashlib
import subprocess
from pathlib import Path
from typing import Iterator

EXCLUDED_DIRS = {
    ".repoindex",
    ".venv",
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
}


def _load_gitignore(root: Path) -> list[str]:
    """
    Load raw ignore patterns from ``.gitignore``.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    list[str]
        Non-comment, non-empty ignore patterns.
    """
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []

    patterns: list[str] = []
    for line in gitignore.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _match_gitignore(path: Path, root: Path, patterns: list[str]) -> bool:
    """
    Check whether a path matches any loaded ignore patterns.

    Parameters
    ----------
    path : pathlib.Path
        Candidate path to evaluate.
    root : pathlib.Path
        Repository root used to compute relative paths.
    patterns : list[str]
        Ignore patterns loaded from ``.gitignore``.

    Returns
    -------
    bool
        ``True`` when the path matches at least one pattern.
    """
    rel = str(path.relative_to(root))

    for pat in patterns:
        if pat.endswith("/"):
            if any(part == pat.rstrip("/") for part in path.parts):
                return True
        elif fnmatch.fnmatch(rel, pat):
            return True

    return False


def _is_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    """
    Decide whether a path should be excluded from scanning.

    Parameters
    ----------
    path : pathlib.Path
        Candidate path to evaluate.
    root : pathlib.Path
        Repository root used to compute relative paths.
    patterns : list[str]
        Ignore patterns loaded from ``.gitignore``.

    Returns
    -------
    bool
        ``True`` when the path belongs to an excluded directory or matches
        an ignore pattern.
    """
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True

    if _match_gitignore(path, root, patterns):
        return True

    return False


def _iter_python_files(root: Path) -> Iterator[Path]:
    """
    Yield Python files from a filesystem scan.

    Parameters
    ----------
    root : pathlib.Path
        Repository root to scan recursively.

    Returns
    -------
    collections.abc.Iterator[pathlib.Path]
        Python source files that survive exclusion filtering.
    """
    patterns = _load_gitignore(root)

    for path in root.rglob("*.py"):
        if _is_excluded(path, root, patterns):
            continue
        yield path


def iter_project_files(root: Path) -> Iterator[Path]:
    """
    Yield Python files for indexing.

    Parameters
    ----------
    root : pathlib.Path
        Repository root to inspect.

    Returns
    -------
    collections.abc.Iterator[pathlib.Path]
        Python files selected for indexing.

    Raises
    ------
    subprocess.CalledProcessError
        If ``git ls-files`` fails for a reason other than "not a git
        repository".

    Notes
    -----
    If the root is inside a Git repository, only tracked Python files are used
    so Git remains the source of truth. Outside Git repositories, the function
    falls back to a filesystem scan filtered by ``.gitignore`` rules.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "*.py"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )

        files = [
            root / line.strip() for line in result.stdout.splitlines() if line.strip()
        ]

        return iter(sorted(files))

    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        # fallback only if git is unavailable or not a repository
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = (exc.stderr or "").lower()
            if "not a git repository" not in stderr:
                raise

        return iter(sorted(_iter_python_files(root)))


def file_metadata(path: Path) -> dict[str, object]:
    """
    Collect stable metadata for a file.

    Parameters
    ----------
    path : pathlib.Path
        File whose metadata should be collected.

    Returns
    -------
    dict[str, object]
        File path, hash, modification time, and size.
    """
    data = path.read_bytes()
    return {
        "path": str(path),
        "hash": hashlib.sha256(data).hexdigest(),
        "mtime": path.stat().st_mtime,
        "size": path.stat().st_size,
    }
