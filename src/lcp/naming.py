"""Package name normalization for registry paths."""

from __future__ import annotations

import re

_NORMALIZE_RE = re.compile(r"[-_.]+")


def normalize_package_name(name: str) -> str:
    """Normalize a package name to its canonical registry slug.

    Applies PEP 503-style normalization: runs of ``-``, ``_`` and ``.``
    are collapsed into a single ``-`` and the result is lowercased. This
    is the canonical form used for registry folder paths, so a package
    imported as ``google.adk`` maps to the slug ``google-adk`` and is
    stored under ``manifests/python/g/google-adk/``.

    Args:
        name: Raw package or import name (e.g. ``"google.adk"``).

    Returns:
        Normalized slug suitable for registry paths
        (e.g. ``"google-adk"``).
    """
    return _NORMALIZE_RE.sub("-", name.strip()).strip("-").lower()
