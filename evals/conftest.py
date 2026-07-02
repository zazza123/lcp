"""Make the evals directory importable in tests (harness is not an installed package)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
