from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator


def iter_python_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*.py"):
        if ".repoindex" in path.parts:
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
