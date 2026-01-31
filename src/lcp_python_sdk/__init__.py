"""LCP Python SDK - Generate Library Context Protocol files from Python packages."""

from .generator import generate_lcp
from .models import (
    LCPDocument,
    Library,
    Manifest,
    Param,
    Semantics,
    Signature,
    Symbol,
    SymbolKind,
)
from .scanner import scan_package
from .validator import (
    LCPValidationError,
    is_valid,
    validate_document,
    validate_file,
    validate_or_raise,
)

__version__ = "0.1.0"
__all__ = [
    # Main function
    "scan",
    # Models
    "LCPDocument",
    "Library",
    "Manifest",
    "Param",
    "Semantics",
    "Signature",
    "Symbol",
    "SymbolKind",
    # Scanner
    "scan_package",
    # Generator
    "generate_lcp",
    # Validator
    "validate_document",
    "validate_file",
    "validate_or_raise",
    "is_valid",
    "LCPValidationError",
]


def scan(
    package_name: str,
    *,
    include_private: bool = False,
    recursive: bool = True,
    validate: bool = True,
) -> LCPDocument:
    """Scan a Python package and generate an LCP document.

    This is the main entry point for the SDK.

    Args:
        package_name: The name of an installed Python package to scan.
        include_private: Include private symbols (starting with _).
        recursive: Scan submodules recursively.
        validate: Validate the output against the LCP schema.

    Returns:
        An LCPDocument containing the scanned library information.

    Raises:
        ImportError: If the package cannot be imported.
        LCPValidationError: If validation is enabled and the output is invalid.

    Example:
        >>> from lcp_python_sdk import scan
        >>> doc = scan("json")
        >>> doc.to_file("json.lcp.json")
    """
    scanned = scan_package(
        package_name,
        include_private=include_private,
        recursive=recursive,
    )

    lcp_doc = generate_lcp(scanned)

    if validate:
        validate_or_raise(lcp_doc)

    return lcp_doc
