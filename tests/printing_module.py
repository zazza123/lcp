"""Fixture: a module that prints to stdout at import time (protocol hygiene)."""

print("import-time noise on stdout")


def documented(x: int) -> int:
    """Return x unchanged."""
    return x
