"""Fixture exercising environment-derived values (#72).

A real on-disk module so ``inspect.getsource`` can recover the AST.
"""

import os
import sys
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
