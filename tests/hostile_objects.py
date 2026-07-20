"""Hostile fixture objects that raise RuntimeError from attribute access.

These classes exist to prove that ``isinstance()`` is not safe to call on
arbitrary objects. CPython's ``isinstance()`` has a fast path that checks
``type(obj)`` directly, but when that fast check misses it falls back to
reading ``value.__class__``, which goes through ``__getattribute__`` (or,
for a plain missing attribute, ``__getattr__``). A hostile proxy object can
raise from that path.

Critically, the fixtures below raise ``RuntimeError``, not
``AttributeError``. This is deliberate and must not be "fixed": Flask's
``flask.request`` raises ``RuntimeError("working outside of request
context")`` when accessed outside a request, and that is exactly the shape
of exception ``_is_constant``/``_constant_summary`` must survive without
crashing. An ``AttributeError`` raised from ``__getattr__`` or
``__getattribute__`` is silently swallowed by ``isinstance()`` (it just
returns ``False``); a ``RuntimeError`` is not swallowed and propagates
straight out of ``isinstance()``. So a fixture that raised ``AttributeError``
would pass even against unfixed code that calls a bare
``isinstance(value, _PRIMITIVE_TYPES)`` -- it would prove nothing about the
bug these tests exist to catch.

CodeQL's "non-standard exception raised in special method" rule flags
``__getattr__``/``__getattribute__`` implementations that raise anything
other than ``AttributeError`` and suggests raising ``AttributeError``
instead. Do NOT apply that suggestion here: doing so would turn these tests
into false negatives that pass whether or not the scanner is actually safe
against ``RuntimeError``-raising proxies like ``flask.request``. This module
is listed in ``paths-ignore`` in ``.github/workflows/codeql.yml`` for
precisely this reason.
"""


class Hostile:
    """Raises RuntimeError from ``__getattr__`` for any missing attribute."""

    def __getattr__(self, item):
        raise RuntimeError("working outside of request context")


class HostileProxy:
    """Raises RuntimeError from ``__getattribute__`` for any attribute access.

    Unlike :class:`Hostile`, this intercepts *every* attribute access (not
    just misses), which is what forces ``isinstance()``'s ``__class__``
    fallback path specifically.
    """

    def __getattribute__(self, item):
        raise RuntimeError("working outside of request context")
