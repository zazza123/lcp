"""Implementation module holding the real definitions."""


class Thing:
    """A class defined in the sibling implementation package."""

    def method(self):
        """A method on the implementation class."""
        return 1


def thing_func(x):
    """A function defined in the sibling implementation package."""
    return x


class _Sentinel:
    """A module-level sentinel (models firestore's SERVER_TIMESTAMP)."""

    def __repr__(self):
        return "<sentinel>"


#: A value re-exported by the facade whose class lives in the sibling but which
#: has no __name__ (like SERVER_TIMESTAMP). scan_module drops it; the shape-A
#: value post-pass captures it at the facade.
SERVER_TS = _Sentinel()
