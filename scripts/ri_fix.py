#!/usr/bin/env python3
"""
repoindex → Codex bridge (ri-fix)

Generate a deterministic prompt for code modification tasks
based on repoindex context.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: ri-fix <query>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    try:
        result = subprocess.run(
            ["repoindex", "context-for", query, "--prompt"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stderr)
        sys.exit(exc.returncode)

    print(result.stdout)


if __name__ == "__main__":
    main()
