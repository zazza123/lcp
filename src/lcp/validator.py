"""Validator module for LCP documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator, ValidationError

from .models import LCPDocument


# Load schema from package
_SCHEMA_PATH = Path(__file__).parent / "schema.json"


def _load_schema() -> dict[str, Any]:
    """Load the LCP v1 JSON schema."""
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_dict(data: dict[str, Any]) -> list[str]:
    """Validate a dictionary against the LCP v1 schema.

    Args:
        data: The LCP document as a dictionary.

    Returns:
        A list of validation error messages. Empty list if valid.
    """
    schema = _load_schema()
    validator = Draft202012Validator(schema)

    errors = []
    for error in validator.iter_errors(data):
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
        errors.append(f"{path}: {error.message}")

    return errors


def validate_document(doc: LCPDocument) -> list[str]:
    """Validate an LCPDocument against the LCP v1 schema.

    Args:
        doc: The LCPDocument to validate.

    Returns:
        A list of validation error messages. Empty list if valid.
    """
    return validate_dict(doc.to_dict())


def validate_file(path: str | Path) -> list[str]:
    """Validate an LCP file against the LCP v1 schema.

    Args:
        path: Path to the LCP JSON file.

    Returns:
        A list of validation error messages. Empty list if valid.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return validate_dict(data)


def is_valid(doc: LCPDocument | dict[str, Any]) -> bool:
    """Check if an LCP document is valid.

    Args:
        doc: The LCPDocument or dictionary to validate.

    Returns:
        True if valid, False otherwise.
    """
    if isinstance(doc, LCPDocument):
        return len(validate_document(doc)) == 0
    return len(validate_dict(doc)) == 0


class LCPValidationError(Exception):
    """Exception raised when LCP validation fails."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        message = f"LCP validation failed with {len(errors)} error(s):\n" + "\n".join(
            f"  - {e}" for e in errors[:10]
        )
        if len(errors) > 10:
            message += f"\n  ... and {len(errors) - 10} more errors"
        super().__init__(message)


def validate_or_raise(doc: LCPDocument | dict[str, Any]) -> None:
    """Validate an LCP document and raise if invalid.

    Args:
        doc: The LCPDocument or dictionary to validate.

    Raises:
        LCPValidationError: If the document is invalid.
    """
    if isinstance(doc, LCPDocument):
        errors = validate_document(doc)
    else:
        errors = validate_dict(doc)

    if errors:
        raise LCPValidationError(errors)
