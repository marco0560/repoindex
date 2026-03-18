from __future__ import annotations

import fnmatch
import hashlib
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


def iter_python_files(root: Path) -> Iterator[Path]:
    patterns = _load_gitignore(root)

    for path in root.rglob("*.py"):
        if _is_excluded(path, root, patterns):
            continue
        yield path


def file_metadata(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "path": str(path),
        "hash": hashlib.sha256(data).hexdigest(),
        "mtime": path.stat().st_mtime,
        "size": path.stat().st_size,
    }
