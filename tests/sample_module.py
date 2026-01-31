"""Sample module for testing the LCP scanner."""


MODULE_VERSION = "1.0.0"
MAX_ITEMS = 100


def simple_function(x: int, y: int) -> int:
    """Add two numbers together.

    This is a simple function that demonstrates basic arithmetic.

    Args:
        x: The first number.
        y: The second number.

    Returns:
        The sum of x and y.
    """
    return x + y


def function_with_defaults(
    name: str,
    count: int = 10,
    enabled: bool = True,
) -> str:
    """A function with default parameter values.

    Args:
        name: The name to use.
        count: Number of iterations.
        enabled: Whether the feature is enabled.

    Returns:
        A formatted string.
    """
    return f"{name}: {count}, enabled={enabled}"


async def async_function(url: str) -> dict:
    """An asynchronous function.

    Args:
        url: The URL to fetch.

    Returns:
        The response data.
    """
    return {"url": url}


def function_without_types(a, b):
    """A function without type annotations."""
    return a + b


def _private_function(x: int) -> int:
    """A private function that should be excluded by default."""
    return x * 2


class SimpleClass:
    """A simple class for testing.

    This class demonstrates basic class structure with methods and attributes.
    """

    class_attribute: str = "default"

    def __init__(self, value: int) -> None:
        """Initialize the class.

        Args:
            value: The initial value.
        """
        self.value = value

    def instance_method(self, multiplier: int = 1) -> int:
        """Multiply the value.

        Args:
            multiplier: The multiplier to use.

        Returns:
            The multiplied value.
        """
        return self.value * multiplier

    @property
    def doubled(self) -> int:
        """Return the value doubled."""
        return self.value * 2

    @classmethod
    def from_string(cls, s: str) -> "SimpleClass":
        """Create an instance from a string.

        Args:
            s: The string representation of an integer.

        Returns:
            A new SimpleClass instance.
        """
        return cls(int(s))

    @staticmethod
    def static_helper(x: int) -> int:
        """A static helper method.

        Args:
            x: The input value.

        Returns:
            The input plus one.
        """
        return x + 1

    def _private_method(self) -> None:
        """A private method."""
        pass


class ChildClass(SimpleClass):
    """A child class that inherits from SimpleClass."""

    def child_method(self) -> str:
        """A method specific to the child class."""
        return "child"


class ClassWithoutDocstring:
    def method_without_docstring(self, x):
        return x
