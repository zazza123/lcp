"""Implementation module holding a C-function-like callable (deferred to #63)."""


class _CFuncLike:
    def __call__(self, *args, **kwargs):
        return None


#: Callable with a recoverable signature -> classified "defer", not captured.
cfunc = _CFuncLike()
