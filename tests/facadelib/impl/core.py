"""Implementation module holding the real definitions."""


class Thing:
    """A class defined in the sibling implementation package."""

    def method(self):
        """A method on the implementation class."""
        return 1


def thing_func(x):
    """A function defined in the sibling implementation package."""
    return x


#: A public value re-exported by the facade.
THING_LIMIT = 100
