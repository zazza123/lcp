"""The facade package (mirrors google.cloud.firestore).

Re-exports names defined in the sibling `facadelib.impl.*` and one name from a
foreign top-level `otherlib.core`.
"""

from facadelib.impl.core import SERVER_TS, Thing, thing_func
from facadelib.impl.deferred import cfunc
from otherlib.core import Foreign

__all__ = ["Thing", "thing_func", "SERVER_TS", "cfunc", "Foreign"]
