"""Version lookup helpers for repoindex.

Responsibilities
----------------
- Expose the package version without requiring the generated ``_version.py`` file.
- Prefer build-generated SCM metadata when it is present.
- Fall back to installed package metadata or a deterministic default in source checkouts.

Design principles
-----------------
Version lookup stays lightweight and safe for editable source trees where
generated files may be absent.

Architectural role
------------------
This module belongs to the **package infrastructure layer** and decouples
runtime version access from generated source artifacts.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version


def package_version() -> str:
    """
    Return the current repoindex version string.

    Parameters
    ----------
    None

    Returns
    -------
    str
        The build-generated version when available, otherwise the installed
        package metadata version, otherwise ``"0.0.0"``.
    """
    try:
        from ._version import version as generated_version
    except ImportError:
        try:
            return metadata_version("repoindex")
        except PackageNotFoundError:
            return "0.0.0"
    return generated_version
