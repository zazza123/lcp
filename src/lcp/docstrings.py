"""Structured docstring extraction for the generator (spec D11).

Wraps ``docstring_parser`` behind a single fail-open entry point: any
parser exception yields ``None`` and the caller keeps today's behavior
(summary + raw description). This module is only used at generate time —
the scanner captures raw docstrings but never parses them during member
iteration, so hostile-package resilience is unaffected.
"""

from __future__ import annotations

import doctest
import inspect
from dataclasses import dataclass, field

from docstring_parser import parse as _parse
from docstring_parser.common import DocstringExample


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


def _render_doctest_block(text: str) -> tuple[str, str | None]:
    """Re-render a doctest block as canonical ``>>>`` code plus prose.

    Uses the stdlib doctest parser so statements, continuation lines and
    expected output are split exactly like the doctest runner would.
    """
    pieces = doctest.DocTestParser().parse(text)
    code_lines: list[str] = []
    prose: list[str] = []
    for piece in pieces:
        if isinstance(piece, doctest.Example):
            source = piece.source.rstrip("\n").split("\n")
            code_lines.append(">>> " + source[0])
            code_lines.extend("... " + line for line in source[1:])
            if piece.want:
                code_lines.extend(piece.want.rstrip("\n").split("\n"))
        elif piece.strip():
            prose.append(piece.strip())
    return "\n".join(code_lines), "\n\n".join(prose) or None


def _extract_examples(meta: DocstringExample) -> list[tuple[str, str | None]]:
    """Turn one Examples-section meta entry into ``(code, description)``."""
    text = "\n".join(part for part in (meta.snippet, meta.description) if part)
    if not text.strip():
        return []
    if ">>>" not in text:
        # Fenced/indented (non-doctest) example code is taken verbatim.
        return [(text.strip(), None)]
    code, prose = _render_doctest_block(text)
    if not code:
        return []
    return [(code, prose)]


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
        for meta in parsed.meta:
            if isinstance(meta, DocstringExample):
                try:
                    extras.examples.extend(_extract_examples(meta))
                except Exception:
                    # A malformed doctest must not discard params/raises.
                    continue
        return None if extras.is_empty() else extras
    except Exception:
        return None
