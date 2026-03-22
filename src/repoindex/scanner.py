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
    rel = str(path.relative_to(root))

    for pat in patterns:
        if pat.endswith("/"):
            if any(part == pat.rstrip("/") for part in path.parts):
                return True
        elif fnmatch.fnmatch(rel, pat):
            return True

    return False


def _is_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True

    if _match_gitignore(path, root, patterns):
        return True

    return False


def _iter_python_files(root: Path) -> Iterator[Path]:
    patterns = _load_gitignore(root)

    for path in root.rglob("*.py"):
        if _is_excluded(path, root, patterns):
            continue
        yield path


def iter_project_files(root: Path) -> Iterator[Path]:
    """
    Yield Python files for indexing.

    Behavior
    --------
    - If inside a Git repository: use tracked files (deterministic SOT)
    - Otherwise: fall back to filesystem scan with .gitignore filtering

    This ensures the tool works both inside and outside Git repositories.
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
    data = path.read_bytes()
    return {
        "path": str(path),
        "hash": hashlib.sha256(data).hexdigest(),
        "mtime": path.stat().st_mtime,
        "size": path.stat().st_size,
    }
