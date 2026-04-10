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


def installed_distribution_version(distribution_name: str) -> str | None:
    """
    Return the installed version for one distribution when available.

    Parameters
    ----------
    distribution_name : str
        Installed distribution name queried through package metadata.

    Returns
    -------
    str | None
        Installed distribution version, or ``None`` when the distribution is
        not installed in the current environment.
    """
    try:
        return metadata_version(distribution_name)
    except PackageNotFoundError:
        return None


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
        installed_version = installed_distribution_version("repoindex")
        if installed_version is None:
            return "0.0.0"
        return installed_version
    return generated_version
