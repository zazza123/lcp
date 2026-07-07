"""Fixture: a module whose import blocks (timeout / concurrency tests).

Sleep length is read from LCP_TEST_IMPORT_SLEEP so tests choose their own
duration; the default is long enough that a missing override always trips
the scan timeout rather than passing by accident.
"""

import os
import time

time.sleep(float(os.environ.get("LCP_TEST_IMPORT_SLEEP", "30")))
