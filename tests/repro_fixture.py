"""Fixture exercising environment-derived values (#72).

A real on-disk module so ``inspect.getsource`` can recover the AST.
"""

import os
import sys

# Environment-derived path constant → symbolic form expected in the summary.
DATA_ROOT = os.path.join(sys.prefix, "share", "data")

# Non-environment constants → must stay verbatim in the summary.
GREETING = "GET"
MAX_RETRIES = 3


def connect(exe=sys.executable, cache=os.path.expanduser("~/.cache/app"), retries=3):
    """Fixture with env-derived defaults (``exe``, ``cache``) and a plain one."""
    return exe, cache, retries
