"""Structured docstring extraction for the generator (spec D11).

Wraps ``docstring_parser`` behind a single fail-open entry point: any
parser exception yields ``None`` and the caller keeps today's behavior
(summary + raw description). This module is only used at generate time —
the scanner captures raw docstrings but never parses them during member
iteration, so hostile-package resilience is unaffected.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field

from docstring_parser import parse as _parse


@dataclass
class DocstringExtras:
    """Structured fields extracted from one docstring.

    ``param_descriptions`` is keyed by the parameter name with ``*``/``**``
    stripped, so it can be merged with introspected params by name.
    ``raises`` holds ``(exception type, condition)`` pairs and ``examples``
    holds ``(code, description)`` pairs.
    """

    param_descriptions: dict[str, str] = field(default_factory=dict)
    raises: list[tuple[str, str | None]] = field(default_factory=list)
    returns_description: str | None = None
    examples: list[tuple[str, str | None]] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Whether nothing structured was extracted."""
        return (
            not self.param_descriptions
            and not self.raises
            and self.returns_description is None
            and not self.examples
        )


def extract_structured(docstring: object) -> DocstringExtras | None:
    """Extract structured fields from a raw docstring, fail-open.

    Args:
        docstring: The raw ``__doc__`` value; anything non-string (some
            classes expose ``__doc__`` as a descriptor) is treated as no
            docstring.

    Returns:
        The extracted fields, or ``None`` when the input is not a usable
        string, the parser raised, or nothing structured was found.
    """
    if not isinstance(docstring, str) or not docstring.strip():
        return None
    try:
        parsed = _parse(inspect.cleandoc(docstring))
        extras = DocstringExtras()
        for param in parsed.params:
            name = (param.arg_name or "").lstrip("*")
            if name and param.description:
                extras.param_descriptions[name] = param.description.strip()
        for entry in parsed.raises:
            if entry.type_name:
                condition = (entry.description or "").strip() or None
                extras.raises.append((entry.type_name, condition))
        if parsed.returns is not None and parsed.returns.description:
            extras.returns_description = parsed.returns.description.strip()
        return None if extras.is_empty() else extras
    except Exception:
        return None
