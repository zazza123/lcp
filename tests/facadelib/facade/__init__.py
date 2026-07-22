"""The facade package (mirrors google.cloud.firestore).

Re-exports names defined in the sibling `facadelib.impl.*` and one name from a
foreign top-level `otherlib.core`.
"""

from facadelib.impl.core import THING_LIMIT, Thing, thing_func
from facadelib.impl.deferred import cfunc
from otherlib.core import Foreign

__all__ = ["Thing", "thing_func", "THING_LIMIT", "cfunc", "Foreign"]
