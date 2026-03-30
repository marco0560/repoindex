"""Top-level package for repoindex.

Responsibilities
----------------
- Expose package version metadata through `__version__`.
- Re-export major entrypoints or helper symbols for convenience.

Design principles
-----------------
The initializer stays minimal, avoiding heavy imports while providing essential metadata.

Architectural role
------------------
This module belongs to the **package infrastructure layer** and anchors repoindex versioning and exports.
"""

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0"
