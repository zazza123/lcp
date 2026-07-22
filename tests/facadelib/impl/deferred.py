"""Implementation module holding a C-function-like callable (deferred to #63)."""


class _CFuncLike:
    __name__ = "cfunc"
    __module__ = "facadelib.impl.deferred"

    def __call__(self, *args, **kwargs):
        return None


#: Callable with a recoverable signature but classified "defer" (looks like a
#: C function). Has __name__/__module__, so scan_module records it; shape A then
#: defers capture to #63, leaving the record dangling (reported as unresolved).
cfunc = _CFuncLike()
