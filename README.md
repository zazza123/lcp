# lcp-python-sdk

Python SDK for generating [Library Context Protocol (LCP)](https://lcp.dev) files from Python packages.

## Installation

```bash
pip install lcp-python-sdk
```

## Usage

### CLI

```bash
# Scan a package and output LCP JSON
lcp-python scan requests -o requests.lcp.json

# Include private symbols
lcp-python scan mypackage --include-private

# Skip validation
lcp-python scan mypackage --no-validate
```

### Python API

```python
from lcp_python_sdk import scan

# Scan a package
lcp_doc = scan("requests")

# Save to file
lcp_doc.to_file("requests.lcp.json")

# Get as dict
data = lcp_doc.to_dict()

# Include private symbols
lcp_doc = scan("mypackage", include_private=True)
```

## Features

- Scans installed Python packages using `inspect` and `ast` modules
- Generates LCP v1 compliant JSON files
- Extracts functions, classes, methods, attributes, and constants
- Parses docstrings for summaries and descriptions
- Extracts type hints from function signatures
- Validates output against LCP JSON schema
- Both CLI and Python API interfaces

## License

MIT

Resume this session with copilot --resume=ba62e74c-ca8c-4ca6-82b8-4895b5a046fa