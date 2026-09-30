"""Class shapes that exercise inspect's class source lookup (#80).

Each class here stresses one rule of CPython's ``inspect._ClassFinder``, which
the scanner's per-file class index must reproduce exactly.
"""


def _decorate(cls):
    return cls


class Plain:
    """A top-level class with no decorators."""

    value = 1


@_decorate
class Decorated:
    """Its source starts at the decorator line, not the ``class`` line."""


@_decorate
@_decorate
class DoublyDecorated:
    """Its source starts at the first decorator."""


class Outer:
    """Nested classes are found by dotted qualname."""

    class Inner:
        class Deepest:
            pass


def _factory():
    class Local:
        """Qualname carries a ``<locals>`` segment."""

    return Local


Local = _factory()


async def _async_factory():
    class AsyncLocal:
        pass

    return AsyncLocal


class Redefined:
    """The first definition: what inspect reports for either binding."""

    first = True


FirstRedefined = Redefined


class Redefined:  # noqa: F811 - deliberate: inspect matches the first one
    """The runtime binding, whose source inspect still reports as the first."""

    second = True


class MultiLine(
    Plain,
):
    """A header split over several lines."""

    text = """
    class NotAClass:
        pass
    """
