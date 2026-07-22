"""Synthetic re-export fixtures for facade thin re-export scanning (#67).

Each object simulates a public name a facade re-exports from a foreign
dependency ``fakedep``: its ``__module__`` (directly, or via its type) points
outside any scanned package.
"""


class _ReexportBase:
    __module__ = "fakedep.base"

    def inherited_method(self):
        """A method inherited from a base in another dependency submodule."""
        return 2


class ReexportedClass(_ReexportBase):
    """A class re-exported from a dependency."""

    __module__ = "fakedep.core"

    def method(self):
        """A method defined on the re-exported class."""
        return 1


def reexported_function(x):
    """A function re-exported from a dependency."""
    return x


reexported_function.__module__ = "fakedep.core"


class _SignalType:
    __module__ = "fakedep.signals"


#: Non-callable value whose type is library-defined -> captured as constant.
reexported_signal = _SignalType()


class _ProxyType:
    __module__ = "fakedep.local"

    def __call__(self, *args, **kwargs):
        return None

    @property
    def __signature__(self):
        raise RuntimeError("working outside of context")


#: Callable value whose signature() raises -> captured as constant.
reexported_proxy = _ProxyType()


class _CFuncLike:
    __module__ = "fakedep.core"

    def __call__(self, *args, **kwargs):
        return None


#: Callable with a recoverable signature -> a C function, captured as function (#63).
reexported_cfunc = _CFuncLike()
