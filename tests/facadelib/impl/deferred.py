"""Implementation module holding a C-function-like callable (captured by #63)."""


class _CFuncLike:
    __name__ = "cfunc"
    __module__ = "facadelib.impl.deferred"

    def __call__(self, *args, **kwargs):
        return None


#: Callable with a recoverable signature (looks like a C function). Has
#: __name__/__module__, so it is captured as a function at its def-site (#63).
cfunc = _CFuncLike()
