# Python Package Publishing Walkthrough

## Purpose

This note records the maintainer workflow for publishing `repoindex` and its
first-party plugin packages so end users can install the official bundle
through standard `pip` package-name resolution.

## Audience

This document is for maintainers, not end users.

End users should only need the documented install command, while maintainers
need to understand what `pip` resolves, what must be published, and what order
to publish packages in.

## Packaging Model

The current repository contains these installable distributions:

* `repoindex`
* `repoindex-analyzer-c`
* `repoindex-analyzer-bash`
* `repoindex-bundle-official`

The intended end-user install target is:

```bash
pip install repoindex-bundle-official
```

The compatible extra-based surface remains:

```bash
pip install "repoindex[bundle-official]"
```

## How `pip` Resolves Package Names

When `pip` sees a dependency such as:

* `repoindex-analyzer-c`
* `repoindex-analyzer-bash`
* `sentence-transformers>=3.0`

it does not inspect arbitrary subdirectories in a Git checkout.

Instead it:

1. reads dependency metadata from the package being installed
2. asks the configured package index for each dependency name
3. downloads a wheel or source distribution for each resolved package

That means a monorepo layout such as `packages/repoindex-analyzer-c/` is not
enough by itself for normal end-user installation. For `pip` to resolve those
names seamlessly, the packages must be published to a package index or
installed explicitly by path.

## What Must Be Published

For the official bundle experience to work without local-path knowledge,
publish at least:

* `repoindex`
* `repoindex-analyzer-c`
* `repoindex-analyzer-bash`
* `repoindex-bundle-official`

The bundle package is the primary end-user target. The root extra remains a
compatible secondary surface.

## Version Policy

Current policy while the repository stays a monorepo:

* `repoindex` uses SCM-managed versioning
* `repoindex-analyzer-c` uses a manually managed version
* `repoindex-analyzer-bash` uses a manually managed version
* `repoindex-bundle-official` uses a manually managed version

Independent SCM-managed analyzer versioning is deferred until each analyzer
has its own repository and therefore its own tag stream.

## Build Concepts

### Wheel

A wheel (`.whl`) is the standard built Python package format.

It is a ready-to-install archive that lets `pip` install a package without
running a full build step on the user's machine.

### Source Distribution

A source distribution (`.tar.gz`) contains the source package and requires a
local build step during installation.

For end-user experience, wheels are preferred whenever possible.

## Required Accounts And Tools

Create accounts on:

* PyPI
* TestPyPI

Install local release tools in a dedicated environment:

```bash
python -m venv .venv-release
source .venv-release/bin/activate
python -m pip install --upgrade pip build twine
```

## Preflight Checks

Before publishing:

1. verify package names are available on PyPI
2. verify versions are the intended release versions
3. build every distribution
4. run `twine check` on every generated artifact

## Build Steps

From the repository root:

Build `repoindex`:

```bash
python -m build
```

Build `repoindex-analyzer-c`:

```bash
cd packages/repoindex-analyzer-c
python -m build
cd ../..
```

Build `repoindex-analyzer-bash`:

```bash
cd packages/repoindex-analyzer-bash
python -m build
cd ../..
```

Build `repoindex-bundle-official`:

```bash
cd packages/repoindex-bundle-official
python -m build
cd ../..
```

## Artifact Validation

Validate built artifacts before upload:

```bash
python -m twine check dist/*
python -m twine check packages/repoindex-analyzer-c/dist/*
python -m twine check packages/repoindex-analyzer-bash/dist/*
python -m twine check packages/repoindex-bundle-official/dist/*
```

## Recommended Release Order

Publish in this order:

1. `repoindex-analyzer-c`
2. `repoindex-analyzer-bash`
3. `repoindex`
4. `repoindex-bundle-official`

This ensures that when the root package or bundle resolves dependency names,
the analyzer distributions already exist in the package index.

## TestPyPI Rehearsal

Upload to TestPyPI first:

```bash
python -m twine upload --repository testpypi packages/repoindex-analyzer-c/dist/*
python -m twine upload --repository testpypi packages/repoindex-analyzer-bash/dist/*
python -m twine upload --repository testpypi dist/*
python -m twine upload --repository testpypi packages/repoindex-bundle-official/dist/*
```

Then test installation from a fresh environment:

```bash
python -m venv /tmp/ri-test
source /tmp/ri-test/bin/activate
pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  repoindex-bundle-official
repoindex plugins
```

The extra PyPI index is needed because TestPyPI typically does not host common
third-party dependencies such as `sentence-transformers`.

## Production Upload

Once TestPyPI works, upload to PyPI:

```bash
python -m twine upload packages/repoindex-analyzer-c/dist/*
python -m twine upload packages/repoindex-analyzer-bash/dist/*
python -m twine upload dist/*
python -m twine upload packages/repoindex-bundle-official/dist/*
```

## Final End-User Verification

In a fresh environment:

```bash
python -m venv /tmp/ri-prod
source /tmp/ri-prod/bin/activate
pip install repoindex-bundle-official
repoindex plugins
```

Verify that the expected official analyzers are discoverable.

## Operational Notes

* Use API tokens instead of account passwords for upload.
* Once a version is published on PyPI, that exact version cannot be replaced
  with different contents.
* Treat editable local installs under `packages/` as contributor workflow, not
  as end-user documentation.
* Revisit analyzer versioning only after repository splits make independent
  SCM-managed version streams worthwhile.
