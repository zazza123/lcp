"""Fixture exercising environment-derived values (#72).

A real on-disk module so ``inspect.getsource`` can recover the AST.
"""

import os
import sys
import time
from datetime import datetime

# Environment-derived path constant → symbolic form expected in the summary.
DATA_ROOT = os.path.join(sys.prefix, "share", "data")

# Non-environment constants → must stay verbatim in the summary.
GREETING = "GET"
MAX_RETRIES = 3

# frozenset constant — must render sorted/deterministic (#72 follow-up).
SCHEMES = frozenset({"https", "http", "ftp"})


def connect(exe=sys.executable, cache=os.path.expanduser("~/.cache/app"), retries=3):
    """Fixture with env-derived defaults (``exe``, ``cache``) and a plain one."""
    return exe, cache, retries


def make_tmp(stamp=datetime.now().strftime("%Y%m%d"), sep=os.linesep, label="run"):
    """Computed (Call) default, computed (Attribute) default, and a literal."""
    return stamp, sep, label


def budget(created_at=time.time(), retries=-1, factor=2.0, flag=False):
    """Computed numeric default, a negative literal, a float literal, a bool literal."""
    return created_at, retries, factor, flag


class _Sentinel(int):
    """An int-subclass sentinel, like sqlalchemy's symbol()."""

    def __repr__(self):  # pragma: no cover
        return "sentinel"


_NO_HISTORY = _Sentinel(12345)


def with_sentinel(original=_NO_HISTORY, n=5):
    """A default that is an int-subclass sentinel (computed Name), plus a literal."""
    return original, n
