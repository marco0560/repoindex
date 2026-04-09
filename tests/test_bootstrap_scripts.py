"""Tests for repository bootstrap and package-install helper scripts.

Responsibilities
----------------
- Verify the authoritative first-party editable package list stays deterministic.
- Ensure bootstrap command generation uses the shared package-install helper contract.
- Keep bootstrap and CI package-boundary assumptions aligned to one repository-owned source of truth.

Design principles
-----------------
The tests validate command construction rather than executing package installs,
so packaging drift is caught quickly without network or environment noise.

Architectural role
------------------
This module belongs to the **tooling verification layer** guarding repository-local bootstrap workflows.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from scripts.bootstrap_dev_environment import CommandSpec


class _InstallHelperModule(Protocol):
    """Protocol for the standalone first-party install helper module."""

    FIRST_PARTY_EDITABLE_PACKAGES: tuple[str, ...]

    def editable_package_paths(self, repo_root: Path) -> tuple[Path, ...]:
        """Return package paths in deterministic order."""

    def build_install_argv(self, *, python: str, repo_root: Path) -> tuple[str, ...]:
        """Build the editable-install argv for first-party packages."""


class _PackageInventoryModule(Protocol):
    """Protocol for the shared first-party package inventory helper."""

    FIRST_PARTY_PACKAGE_DIRS: tuple[str, ...]

    def package_paths(self, repo_root: Path) -> tuple[Path, ...]:
        """Return package paths in deterministic order."""


class _BuildHelperModule(Protocol):
    """Protocol for the standalone first-party build helper module."""

    def build_build_argv(self, *, python: str, package_path: Path) -> tuple[str, ...]:
        """Build the wheel+sdist argv for one package."""

    def build_all_argv(
        self,
        *,
        python: str,
        repo_root: Path,
    ) -> tuple[tuple[str, ...], ...]:
        """Build the complete wheel+sdist command plan."""


class _BootstrapHelperModule(Protocol):
    """Protocol for the standalone bootstrap helper module."""

    def build_bootstrap_commands(
        self,
        *,
        repo_root: Path,
        python: str,
        skip_validation: bool,
    ) -> list[CommandSpec]:
        """Build the ordered bootstrap command plan."""


def _load_first_party_package_inventory() -> _PackageInventoryModule:
    """
    Load the shared first-party package inventory helper.

    Parameters
    ----------
    None

    Returns
    -------
    object
        Loaded module object for the shared package inventory helper.
    """
    helper_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "first_party_packages.py"
    )
    spec = importlib.util.spec_from_file_location("first_party_packages", helper_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast("_PackageInventoryModule", module)


def _load_install_helper() -> _InstallHelperModule:
    """
    Load the standalone install helper module from its repository path.

    Parameters
    ----------
    None

    Returns
    -------
    object
        Loaded module object for the install helper script.
    """
    helper_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "install_first_party_packages.py"
    )
    sys.path.insert(0, str(helper_path.parent))
    spec = importlib.util.spec_from_file_location(
        "install_first_party_packages", helper_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast("_InstallHelperModule", module)


def _load_build_helper() -> _BuildHelperModule:
    """
    Load the standalone build helper module from its repository path.

    Parameters
    ----------
    None

    Returns
    -------
    object
        Loaded module object for the build helper script.
    """
    helper_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "build_first_party_packages.py"
    )
    sys.path.insert(0, str(helper_path.parent))
    spec = importlib.util.spec_from_file_location(
        "build_first_party_packages",
        helper_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast("_BuildHelperModule", module)


def _load_bootstrap_helper() -> _BootstrapHelperModule:
    """
    Load the standalone bootstrap helper module from its repository path.

    Parameters
    ----------
    None

    Returns
    -------
    object
        Loaded module object for the bootstrap script.
    """
    helper_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_dev_environment.py"
    )
    spec = importlib.util.spec_from_file_location(
        "bootstrap_dev_environment",
        helper_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast("_BootstrapHelperModule", module)


def test_editable_package_paths_follow_authoritative_first_party_order() -> None:
    """
    Resolve first-party package directories in deterministic install order.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts the helper preserves the accepted first-party package list.
    """
    helper = _load_install_helper()
    repo_root = Path("/tmp/repoindex")

    assert helper.editable_package_paths(repo_root) == (
        repo_root / "packages/repoindex-analyzer-python",
        repo_root / "packages/repoindex-analyzer-json",
        repo_root / "packages/repoindex-analyzer-c",
        repo_root / "packages/repoindex-analyzer-bash",
        repo_root / "packages/repoindex-backend-sqlite",
        repo_root / "packages/repoindex-bundle-official",
    )
    assert helper.FIRST_PARTY_EDITABLE_PACKAGES == (
        "packages/repoindex-analyzer-python",
        "packages/repoindex-analyzer-json",
        "packages/repoindex-analyzer-c",
        "packages/repoindex-analyzer-bash",
        "packages/repoindex-backend-sqlite",
        "packages/repoindex-bundle-official",
    )


def test_shared_first_party_package_inventory_stays_in_split_order() -> None:
    """
    Resolve the shared first-party package inventory in deterministic order.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts the shared package inventory stays aligned with the
        accepted split/package order.
    """
    helper = _load_first_party_package_inventory()
    repo_root = Path("/tmp/repoindex")

    assert helper.package_paths(repo_root) == (
        repo_root / "packages/repoindex-analyzer-python",
        repo_root / "packages/repoindex-analyzer-json",
        repo_root / "packages/repoindex-analyzer-c",
        repo_root / "packages/repoindex-analyzer-bash",
        repo_root / "packages/repoindex-backend-sqlite",
        repo_root / "packages/repoindex-bundle-official",
    )
    assert helper.FIRST_PARTY_PACKAGE_DIRS == (
        "packages/repoindex-analyzer-python",
        "packages/repoindex-analyzer-json",
        "packages/repoindex-analyzer-c",
        "packages/repoindex-analyzer-bash",
        "packages/repoindex-backend-sqlite",
        "packages/repoindex-bundle-official",
    )


def test_build_install_argv_installs_each_first_party_package_editably() -> None:
    """
    Build the exact editable-install command for first-party packages.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts the helper emits the expected pip command arguments.
    """
    helper = _load_install_helper()
    repo_root = Path("/tmp/repoindex")

    assert helper.build_install_argv(
        python="/tmp/repoindex/.venv/bin/python",
        repo_root=repo_root,
    ) == (
        "/tmp/repoindex/.venv/bin/python",
        "-m",
        "pip",
        "install",
        "-e",
        "/tmp/repoindex/packages/repoindex-analyzer-python",
        "-e",
        "/tmp/repoindex/packages/repoindex-analyzer-json",
        "-e",
        "/tmp/repoindex/packages/repoindex-analyzer-c",
        "-e",
        "/tmp/repoindex/packages/repoindex-analyzer-bash",
        "-e",
        "/tmp/repoindex/packages/repoindex-backend-sqlite",
        "-e",
        "/tmp/repoindex/packages/repoindex-bundle-official",
    )


def test_build_helper_rehearses_each_first_party_package_boundary() -> None:
    """
    Build the split-readiness command plan for every first-party package.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts the build helper emits one explicit wheel+sdist
        command per future package repository.
    """
    helper = _load_build_helper()
    repo_root = Path("/tmp/repoindex")

    assert helper.build_all_argv(
        python="/tmp/repoindex/.venv/bin/python",
        repo_root=repo_root,
    ) == (
        (
            "/tmp/repoindex/.venv/bin/python",
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "/tmp/repoindex/packages/repoindex-analyzer-python",
        ),
        (
            "/tmp/repoindex/.venv/bin/python",
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "/tmp/repoindex/packages/repoindex-analyzer-json",
        ),
        (
            "/tmp/repoindex/.venv/bin/python",
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "/tmp/repoindex/packages/repoindex-analyzer-c",
        ),
        (
            "/tmp/repoindex/.venv/bin/python",
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "/tmp/repoindex/packages/repoindex-analyzer-bash",
        ),
        (
            "/tmp/repoindex/.venv/bin/python",
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "/tmp/repoindex/packages/repoindex-backend-sqlite",
        ),
        (
            "/tmp/repoindex/.venv/bin/python",
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "/tmp/repoindex/packages/repoindex-bundle-official",
        ),
    )


def test_build_bootstrap_commands_reuses_shared_first_party_install_command() -> None:
    """
    Reuse the shared first-party install helper inside bootstrap planning.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The test asserts bootstrap no longer hard-codes a divergent package list.
    """
    bootstrap_helper = _load_bootstrap_helper()
    repo_root = Path("/tmp/repoindex")
    commands = bootstrap_helper.build_bootstrap_commands(
        repo_root=repo_root,
        python="/usr/bin/python3",
        skip_validation=True,
    )

    install_command = next(
        command
        for command in commands
        if command.description
        == "Install extracted first-party analyzer and backend packages"
    )

    assert install_command.argv == (
        str(repo_root / ".venv" / "bin" / "python"),
        "scripts/install_first_party_packages.py",
    )
