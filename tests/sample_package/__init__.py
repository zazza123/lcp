"""Sample package fixture for re-export alias scanning."""

from json import loads  # external re-export: must NOT produce an alias
import json  # external module: must stay skipped

from .core import CoreClass, core_function, CONSTANT
from .extras import helper as aliased_helper
