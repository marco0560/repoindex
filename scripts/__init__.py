"""Repository maintenance scripts package.

Responsibilities
----------------
- Group repoindex maintenance entrypoints under one importable namespace.
- Keep documentation for available scripts explicit without importing heavy modules.
- Provide a lightweight package surface for tooling automation.

Design principles
-----------------
The package stays minimal so individual scripts control their dependencies and execution paths.

Architectural role
------------------
This module belongs to the **tooling package layer** exposing repository maintenance helpers.
"""
