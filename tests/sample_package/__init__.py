"""Sample package fixture for re-export alias scanning."""

import json  # external module: must stay skipped
loads = json.loads  # external re-export: must NOT produce an alias

from .core import CoreClass, core_function, CONSTANT
from .extras import helper as aliased_helper
