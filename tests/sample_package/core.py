"""Core module defining the canonical symbols."""

CONSTANT = 42


class CoreClass:
    """A class re-exported at the package root."""

    def do_something(self) -> str:
        """Do something."""
        return "done"


def core_function(x: int) -> int:
    """A function re-exported at the package root."""
    return x + 1


def _private_function() -> None:
    """Never public."""
