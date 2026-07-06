"""Sample package fixture for re-export alias scanning."""

import json  # external module: must stay skipped

from .core import CONSTANT, CoreClass, core_function  # noqa: F401
from .extras import helper as aliased_helper  # noqa: F401

loads = json.loads  # external re-export binding: must NOT produce an alias
