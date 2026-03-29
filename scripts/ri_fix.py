#!/usr/bin/env python3
"""
repoindex → Codex bridge (ri-fix)

Generate a deterministic prompt for code modification tasks
based on repoindex context.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

REPOINDEX_EXE = shutil.which("repoindex") or "repoindex"


def _print_help() -> None:
    """
    Print command usage for ``ri-fix``.

    Parameters
    ----------
    None

    Returns
    -------
    None
        Help text is written to standard output.
    """
    print("Usage: ri-fix <query>")
    print()
    print("Wrapper for: repoindex context-for --prompt <query>")
    print()
    print("Example:")
    print(
        '  ri-fix "Use repoindex to find where context-for builds the prompt '
        'and add a regression test"'
    )


def main() -> None:
    """
    Forward a natural-language query to ``repoindex context-for --prompt``.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The generated prompt is printed to standard output.

    Raises
    ------
    SystemExit
        If no query arguments are provided or the underlying ``repoindex``
        command exits with a non-zero status.
    """
    if len(sys.argv) >= 2 and sys.argv[1] in {"-h", "--help"}:
        _print_help()
        sys.exit(0)

    if len(sys.argv) < 2:
        _print_help()
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    try:
        result = subprocess.run(
            [REPOINDEX_EXE, "context-for", query, "--prompt"],
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
