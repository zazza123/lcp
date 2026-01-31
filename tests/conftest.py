"""Pytest configuration and fixtures."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add tests directory to path for sample_module import
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def sample_module():
    """Import and return the sample module."""
    import sample_module
    return sample_module


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_lcp_dict():
    """Return a minimal valid LCP document as a dict."""
    return {
        "manifest": {
            "schema_version": "1.0",
            "library": {
                "name": "test-lib",
                "version": "1.0.0",
                "language": "python",
            },
        },
        "symbols": {
            "test:func": {
                "kind": "function",
                "semantics": {
                    "summary": "A test function.",
                },
            },
        },
    }


@pytest.fixture
def sample_lcp_file(temp_dir, sample_lcp_dict):
    """Create a temporary LCP file."""
    path = temp_dir / "test.lcp.json"
    with open(path, "w") as f:
        json.dump(sample_lcp_dict, f)
    return path


@pytest.fixture
def invalid_lcp_dict():
    """Return an invalid LCP document."""
    return {
        "manifest": {
            "schema_version": "1.0",
            # Missing required "library" field
        },
        "symbols": {},
    }
