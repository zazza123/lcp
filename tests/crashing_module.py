"""Fixture: a module whose import raises SystemExit (subprocess-scan tests)."""

import sys

sys.exit(1)
