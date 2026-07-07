# Phase 4 — Structured Docstrings + Examples Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `Param.description`, `Signature.raises`, a new additive `Signature.returns_description`, and `Semantics.examples` by parsing Google/NumPy docstrings at generator level, fail-open, with the manifest format frozen at the end of this phase.

**Architecture:** A new `src/lcp/docstrings.py` module wraps `docstring_parser` (spec D11 sign-off) behind a single fail-open entry point `extract_structured()`. The scanner only *captures* the raw docstring on `ScannedSymbol` (no parsing during member iteration — hostile-package resilience preserved); the generator calls `extract_structured()` per symbol and merges docstring params with introspected params **by name** (introspection wins; unmatched docstring entries never invent a `Param`). `semantics.description` stays the full post-summary remainder exactly as today (roadmap code note: "preserve both behaviors") — the structured fields are purely additive, so a parse failure or a skipped merge loses nothing.

**Tech Stack:** Python ≥3.10, `docstring_parser>=0.16` (new **core** dep), stdlib `doctest` for `>>>` blocks, pydantic v2, pytest.

## Global Constraints

- LCP schema version stays `"1.0"`; all manifest additions are additive only. The one model/schema addition (`Signature.returns_description`) was explicitly settled with the user on 2026-07-07 (option: additive field in `models.py` + `schema.json` + `docs/assets/schema.json`, same precedent as Phase 3 `Symbol.aliases`).
- **Fail-open is mandatory:** any parser exception falls back to today's behavior (summary + raw description). Parse at generator level, never during scanner member iteration.
- `semantics.description` keeps the **entire post-summary remainder** (today's behavior, unchanged). Rationale (measured 2026-07-07): `docstring_parser`'s Google parser silently *drops* unknown sections (e.g. `Note:`) that appear after a recognized section, so rebuilding description from parser output would lose information. Duplication cost is bounded and measured against the 2× gzip threshold in Task 8.
- `docstring_parser` is a core dep of the scan/generate path — **not** in the `ai` extra, not needed at MCP-server runtime. DEP commit separate.
- Commits follow the `git-commit-convention` skill (3-letter code; no co-author/session links — public repo). `docs/superpowers` is committed with `git add -f`.
- Docs-alignment rule: spec/guides/plugin skills updated in this same phase via the `lcp-writing-documentation` skill; `mkdocs build --strict` green.
- Eval venv rules: never `pip install -e ".[dev]"` in `evals/.venv` (fastmcp 2.14.4 pinned there); install `docstring_parser` there manually. Main suite gate = no NEW failures vs base (pre-existing pyenv-shim `--version` env failures don't count, see memory).
- **FREEZE NOTE:** Phase 4 is the last phase that touches the manifest format. Additive ideas discovered after this phase are post-launch.
- De-scope line (pre-agreed): if the phase runs long, ship docstring parsing (Tasks 1–2, 4–6) without doctest extraction (Task 3) and move examples to a follow-up.

## Pre-measurements (2026-07-07, dev venv, docstring_parser 0.18.0)

| Library | docstring param entries matched by name | all params gaining description | baseline manifest gzip |
|---|---|---|---|
| fastmcp | 95.8% (436/455) | 22.3% | 287,528 B |
| polars  | 93.3% (764/819) | 53.3% | 640,346 B |
| click   | 98.2% (221/225) | 66.0% | 51,412 B |

Parser exceptions on all three: 0. **Exit criterion X fixed at ≥90%** of docstring-documented params carrying `Param.description` in the generated manifest (the 2–7% gap is renamed/removed params, which must NOT be invented by design). Manifest gzip growth threshold: ≤2× the baselines above.

Parser behavior facts the implementation relies on (verified empirically on 0.18.0):
- Google parser sections: `Args/Arguments/Params/Parameters/Attributes/Example/Examples/Except/Exceptions/Raises/Returns/Yields` only. `Note:`/`See Also:` before the first section stay in `long_description`; after a section they are **dropped** → hence description stays raw.
- Google `DocstringExample`: `snippet=None`, everything (prose + `>>>` lines) in `.description`. NumPy `DocstringExample`: `snippet='>>> code'`, `.description='expected output'`.
- Malformed/hostile inputs (`""`, `":::"`, 100k chars) do not raise — but the try/except stays anyway.

---

### Task 1: DEP — add `docstring_parser` as a core dependency

**Files:**
- Modify: `pyproject.toml:26-31` (the `dependencies` list)

**Interfaces:**
- Produces: `import docstring_parser` available to `src/lcp/` at runtime.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, change the `[project]` dependencies list to:

```toml
dependencies = [
    "pydantic>=2.0",
    "click>=8.0",
    "jsonschema>=4.0",
    "fastmcp>=3.0,<4",
    "docstring_parser>=0.16",
]
```

- [ ] **Step 2: Verify the dev venv resolves it**

Run: `.venv/bin/pip install -e ".[dev]" -q && .venv/bin/python -c "import docstring_parser; print(docstring_parser.__version__)"`
Expected: `0.18.0` (already installed; the editable reinstall just re-validates metadata).

- [ ] **Step 3: Run the full suite (baseline for the phase)**

Run: `.venv/bin/python -m pytest -q`
Expected: same failures as base (pre-existing `--version` env failures only). Note the exact count for the end-of-phase gate.

- [ ] **Step 4: Commit (separate DEP commit, per phase brief)**

Use the `git-commit-convention` skill. Message shape:

```
DEP: Add docstring_parser as a core dependency

Signed off in the v2 surface design spec (D11): core dep of the
scan/generate path, not part of the ai extra, not needed at MCP-server
runtime.
```

---

### Task 2: `src/lcp/docstrings.py` — params / raises / returns extraction (fail-open)

**Files:**
- Create: `src/lcp/docstrings.py`
- Test: `tests/test_docstrings.py` (new)

**Interfaces:**
- Produces:
  - `@dataclass DocstringExtras` with fields `param_descriptions: dict[str, str]`, `raises: list[tuple[str, str | None]]` (type, condition), `returns_description: str | None`, `examples: list[tuple[str, str | None]]` (code, description) — examples stay empty until Task 3.
  - `extract_structured(docstring: object) -> DocstringExtras | None` — returns `None` for non-string/empty input, on any parser exception, and when nothing structured was found (so callers can `if extras:`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_docstrings.py`:

```python
"""Tests for structured docstring extraction (lcp.docstrings)."""

import pytest

from lcp.docstrings import DocstringExtras, extract_structured

GOOGLE = '''Do a thing.

Longer prose here.

Args:
    x (int): The x value.
    missing: Documented but not introspected.

Returns:
    str: The rendered result.

Raises:
    ValueError: If x is negative.
    KeyError: If lookup fails.
'''

NUMPY = '''Compute stuff.

Parameters
----------
x : int
    The x value.

Returns
-------
DataFrame
    A new frame.

Raises
------
ValueError
    If x is bad.
'''


class TestExtractStructured:
    """Google + NumPy extraction of params, raises and returns."""

    def test_google_params(self):
        extras = extract_structured(GOOGLE)
        assert extras.param_descriptions["x"] == "The x value."
        assert (
            extras.param_descriptions["missing"]
            == "Documented but not introspected."
        )

    def test_google_raises(self):
        extras = extract_structured(GOOGLE)
        assert ("ValueError", "If x is negative.") in extras.raises
        assert ("KeyError", "If lookup fails.") in extras.raises

    def test_google_returns_description(self):
        extras = extract_structured(GOOGLE)
        assert extras.returns_description == "The rendered result."

    def test_numpy_style(self):
        extras = extract_structured(NUMPY)
        assert extras.param_descriptions["x"] == "The x value."
        assert extras.returns_description == "A new frame."
        assert extras.raises == [("ValueError", "If x is bad.")]

    def test_indented_docstring_is_cleaned(self):
        # Raw __doc__ keeps the def-site indentation; extraction must cope.
        indented = (
            "Do a thing.\n\n        Args:\n            x: The x value.\n        "
        )
        extras = extract_structured(indented)
        assert extras.param_descriptions["x"] == "The x value."

    def test_variadic_names_normalized(self):
        doc = "Sum.\n\nArgs:\n    *args: Positional.\n    **kwargs: Keyword.\n"
        extras = extract_structured(doc)
        assert extras.param_descriptions == {
            "args": "Positional.",
            "kwargs": "Keyword.",
        }

    @pytest.mark.parametrize("value", [None, "", "   ", 42, object(), b"bytes"])
    def test_non_string_or_empty_returns_none(self, value):
        assert extract_structured(value) is None

    def test_unstructured_docstring_returns_none(self):
        assert extract_structured("Just a summary.\n\nProse only.") is None

    def test_raises_entry_without_type_is_skipped(self):
        # RaisesEntry.type is schema-required; a typeless entry is dropped.
        doc = "Boom.\n\nRaises\n------\n\n    Vague failure text.\n"
        extras = extract_structured(doc)
        assert extras is None or all(t for t, _ in extras.raises)

    def test_fail_open_on_parser_exception(self, monkeypatch):
        import lcp.docstrings as docstrings_mod

        def boom(text):
            raise RuntimeError("parser exploded")

        monkeypatch.setattr(docstrings_mod, "_parse", boom)
        assert extract_structured(GOOGLE) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_docstrings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lcp.docstrings'`

- [ ] **Step 3: Write the implementation**

Create `src/lcp/docstrings.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_docstrings.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

Use `git-commit-convention`. Message shape:

```
ADD: Structured docstring extraction module (params, raises, returns)

New src/lcp/docstrings.py wrapping docstring_parser behind the fail-open
extract_structured() entry point (Google + NumPy). Any parser exception
returns None so the generator keeps today's summary + raw description.
```

---

### Task 3: examples / doctest extraction in `docstrings.py`

**Files:**
- Modify: `src/lcp/docstrings.py`
- Test: `tests/test_docstrings.py`

**Interfaces:**
- Consumes: `DocstringExtras`, `extract_structured` from Task 2.
- Produces: `DocstringExtras.examples` populated as `list[tuple[str, str | None]]` — one entry per `Examples:` section; `code` is the doctest block re-rendered with `>>> `/`... ` prompts and expected output, or the section text verbatim when it contains no `>>>`; `description` is the surrounding prose or `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docstrings.py`:

```python
GOOGLE_EXAMPLES = '''Do a thing.

Examples:
    Basic usage:

    >>> do_thing(1)
    'ok'
    >>> do_thing(2)
    'ok2'
'''

NUMPY_EXAMPLES = '''Compute stuff.

Examples
--------
>>> compute(3)
9
'''

VERBATIM = '''Run it.

Examples:
    result = run(cfg)
    print(result)
'''


class TestExamples:
    """Doctest and verbatim extraction from Examples sections."""

    def test_google_doctest_block(self):
        extras = extract_structured(GOOGLE_EXAMPLES)
        assert len(extras.examples) == 1
        code, description = extras.examples[0]
        assert ">>> do_thing(1)" in code
        assert "'ok'" in code  # expected output preserved
        assert ">>> do_thing(2)" in code
        assert description == "Basic usage:"

    def test_numpy_doctest_block(self):
        extras = extract_structured(NUMPY_EXAMPLES)
        assert len(extras.examples) == 1
        code, _ = extras.examples[0]
        assert ">>> compute(3)" in code
        assert "9" in code

    def test_multiline_doctest_statement(self):
        doc = (
            "T.\n\nExamples:\n"
            "    >>> for i in range(2):\n"
            "    ...     print(i)\n"
            "    0\n"
            "    1\n"
        )
        code, _ = extract_structured(doc).examples[0]
        assert ">>> for i in range(2):" in code
        assert "...     print(i)" in code

    def test_non_doctest_block_verbatim(self):
        extras = extract_structured(VERBATIM)
        code, description = extras.examples[0]
        assert code == "result = run(cfg)\nprint(result)"
        assert description is None

    def test_malformed_doctest_does_not_kill_params(self, monkeypatch):
        import doctest

        def boom(self, text, name="<string>"):
            raise ValueError("bad doctest")

        monkeypatch.setattr(doctest.DocTestParser, "parse", boom)
        extras = extract_structured(GOOGLE + "\nExamples:\n    >>> x(1)\n")
        assert extras.param_descriptions["x"] == "The x value."
        assert extras.examples == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_docstrings.py::TestExamples -v`
Expected: FAIL — `extras.examples` is empty / `extras` is `None` for the examples-only docstrings.

- [ ] **Step 3: Implement extraction**

In `src/lcp/docstrings.py`, add `import doctest` to the imports, add
`from docstring_parser.common import DocstringExample`, and add:

```python
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
```

Then in `extract_structured`, inside the `try`, after the returns handling, add:

```python
        for meta in parsed.meta:
            if isinstance(meta, DocstringExample):
                try:
                    extras.examples.extend(_extract_examples(meta))
                except Exception:
                    # A malformed doctest must not discard params/raises.
                    continue
```

- [ ] **Step 4: Run the whole file's tests**

Run: `.venv/bin/python -m pytest tests/test_docstrings.py -v`
Expected: all PASS (including Task 2's — regression check).

- [ ] **Step 5: Commit**

```
ADD: Doctest and verbatim example extraction from Examples sections

One Example per Examples section: doctest blocks are re-rendered with
canonical >>>/... prompts and expected output via the stdlib doctest
parser; non-doctest blocks are taken verbatim. A malformed doctest is
dropped without discarding the docstring's params/raises/returns.
```

---

### Task 4: scanner captures the raw docstring on `ScannedSymbol`

**Files:**
- Modify: `src/lcp/scanner.py` (dataclass at ~line 46; call sites at ~341, ~360, ~376, ~407, ~458)
- Test: `tests/test_scanner.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ScannedSymbol.docstring: str | None` — the raw `__doc__` when it is a `str`, else `None`. Capture only, **no parsing** (resilience guarantee). Task 6's generator reads this field.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scanner.py` (module-level, near the other `_scan_*` test classes; existing tests define classes/functions locally and call `_scan_function`/`_scan_class` directly — same pattern):

```python
class TestDocstringCapture:
    """The scanner carries the raw docstring for generator-level parsing."""

    def test_scan_function_captures_raw_docstring(self):
        def documented(x):
            """Sum.

            Args:
                x: The value.
            """

        symbol = _scan_function(documented, "pkg.mod")
        assert symbol.docstring == documented.__doc__

    def test_scan_class_captures_raw_docstring_and_members(self):
        class Widget:
            """A widget.

            Args:
                size: The size.
            """

            def render(self, fmt):
                """Render.

                Args:
                    fmt: Format string.
                """

        symbol = _scan_class(Widget, "pkg.mod")
        assert symbol.docstring == Widget.__doc__
        render = next(m for m in symbol.members if m.name == "render")
        assert render.docstring == Widget.render.__doc__

    def test_non_string_doc_captured_as_none(self):
        class WeirdDoc:
            pass

        # sympy-style: __doc__ exposed as a descriptor on the class
        WeirdDoc.__doc__ = property(lambda self: "computed")
        symbol = _scan_class(WeirdDoc, "pkg.mod")
        assert symbol.docstring is None
        assert symbol.summary is None
```

(`_scan_function` is already imported in `tests/test_scanner.py`; make sure `_scan_class` is too — it is, at line 15.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scanner.py::TestDocstringCapture -v`
Expected: FAIL — `ScannedSymbol` has no attribute `docstring` (AttributeError or `None != <docstring>`).

- [ ] **Step 3: Implement capture**

In `src/lcp/scanner.py`:

1. Add a helper right above `_parse_docstring` (~line 110):

```python
def _raw_docstring(doc: Any) -> str | None:
    """Return *doc* when it is a plain string docstring, else ``None``.

    Same non-string guard as ``_parse_docstring``: ``__doc__`` can be a
    descriptor (e.g. sympy) and must never be parsed or stored as-is.
    """
    return doc if isinstance(doc, str) and doc else None
```

2. Add the field to `ScannedSymbol` (after `description: str | None = None`):

```python
    docstring: str | None = None
```

3. Thread it through the five construction sites:
   - `_scan_class` (~341): add `docstring=_raw_docstring(cls.__doc__),` to the class's `ScannedSymbol(...)` at the end of the function (~388).
   - method members (~360-374): add `docstring=_raw_docstring(getattr(obj, "__doc__", None)),`
   - property members (~376-386): add `docstring=_raw_docstring(obj.fget.__doc__ if obj.fget else None),`
   - `_scan_function` (~407-421): add `docstring=_raw_docstring(func.__doc__),`
   - module symbol in `scan_module` (~458-468): add `docstring=_raw_docstring(module.__doc__),`

- [ ] **Step 4: Run the scanner suite**

Run: `.venv/bin/python -m pytest tests/test_scanner.py -v`
Expected: all PASS (new + pre-existing).

- [ ] **Step 5: Commit**

```
ADD: Capture the raw docstring on ScannedSymbol

Data capture only — no parsing happens during member iteration, so the
scanner's hostile-package resilience is unchanged. The generator will
parse the captured docstring fail-open (spec D11).
```

---

### Task 5: additive `Signature.returns_description` (model + schema)

**Files:**
- Modify: `src/lcp/models.py:150-159` (`Signature`)
- Modify: `src/lcp/schema.json` (`$defs.signature.properties`)
- Modify: `docs/assets/schema.json` (same edit — it is the published copy)
- Test: `tests/test_models.py`, `tests/test_validator.py`

**Interfaces:**
- Produces: `Signature.returns_description: str | None = None` (pydantic field, plain name, no alias) and the matching schema property. Task 6's generator sets it; `get_symbol` inherits it via `model_dump(exclude_none=True)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_models.py`:

```python
def test_signature_returns_description_roundtrip():
    sig = Signature(returns="str", returns_description="The rendered result.")
    dumped = sig.model_dump(exclude_none=True, by_alias=True)
    assert dumped["returns_description"] == "The rendered result."
    assert Signature.model_validate(dumped).returns_description == (
        "The rendered result."
    )


def test_signature_returns_description_defaults_to_none():
    assert Signature().returns_description is None
```

(`Signature` may need adding to the imports from `lcp.models` at the top of the file.)

Add to `tests/test_validator.py`, following the pattern of the existing aliases-validation test (a minimal valid document plus the new field):

```python
def test_returns_description_is_valid(self, valid_document):
    doc = copy.deepcopy(valid_document)
    symbol_id = next(iter(doc["symbols"]))
    doc["symbols"][symbol_id]["signatures"] = [
        {
            "params": None,
            "returns": "str",
            "returns_description": "The rendered result.",
        }
    ]
    result = validate_document(doc)
    assert result.valid, result.errors
```

Adapt names to the file's actual fixtures/helpers (there is an existing valid-document fixture used by the Phase 3 aliases test — reuse exactly that pattern, inside the same test class).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py tests/test_validator.py -v -k returns_description`
Expected: model test FAILS (`returns_description` unexpected/absent in dump); validator test FAILS (`additionalProperties` violation).

- [ ] **Step 3: Implement**

In `src/lcp/models.py`, `Signature` becomes:

```python
class Signature(BaseModel):
    """Function/method signature."""

    when: str | None = None
    async_: bool = Field(default=False, alias="async")
    params: list[Param] | None = None
    returns: TypeRef | str | None = None
    returns_description: str | None = None
    raises: list[RaisesEntry] | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)
```

In `src/lcp/schema.json`, inside `$defs.signature.properties`, after the `"returns"` property add:

```json
"returns_description": {
  "type": ["string", "null"],
  "description": "Prose description of the return value, extracted from the docstring."
}
```

Apply the identical edit to `docs/assets/schema.json`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_models.py tests/test_validator.py -v`
Expected: all PASS. Also run `diff <(python -c "import json;print(json.dumps(json.load(open('src/lcp/schema.json')),sort_keys=True))") <(python -c "import json;print(json.dumps(json.load(open('docs/assets/schema.json')),sort_keys=True))")` — the two schema copies must stay identical (empty diff) if they were identical before; if they differed before Phase 4, keep the pre-existing differences and only mirror this addition.

- [ ] **Step 5: Commit**

```
ADD: Additive Signature.returns_description field (model + schema)

Settled 2026-07-07: the docstring's Returns prose needs a home and
type_ref has no description slot. Additive under schema "1.0", same
precedent as Phase 3's Symbol.aliases; docs/assets/schema.json mirrored.
```

---

### Task 6: generator wires structured extras into the models

**Files:**
- Modify: `src/lcp/generator.py` (`_convert_param`, `_convert_signature`, `_convert_symbol`)
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: `extract_structured`, `DocstringExtras` (Task 2/3); `ScannedSymbol.docstring` (Task 4); `Signature.returns_description` (Task 5).
- Produces: generated manifests where `Param.description`, `Signature.raises`, `Signature.returns_description`, `Semantics.examples` are populated; `semantics.summary`/`description` byte-identical to pre-Phase-4 output.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_generator.py` (imports of `RaisesEntry` etc. not needed — assert on the converted objects):

```python
DOCSTRING = '''Do a thing.

Longer prose here.

Args:
    x (int): The x value.
    missing: Documented but not introspected.

Returns:
    str: The rendered result.

Raises:
    ValueError: If x is negative.

Examples:
    >>> do_thing(1)
    'ok'
'''


def _scanned_documented_function():
    return ScannedSymbol(
        name="do_thing",
        qualified_name="do_thing",
        module_path="pkg.mod",
        kind="function",
        summary="Do a thing.",
        description="Longer prose here.\n\nArgs:\n    x (int): The x value.",
        docstring=DOCSTRING,
        signature=ScannedSignature(
            params=[ScannedParam(name="x", type_hint="int")],
            return_type="str",
        ),
    )


class TestStructuredDocstrings:
    """Generator merges docstring extras into the LCP models (spec D11)."""

    def test_param_description_merged_by_name(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        params = symbol.signatures[0].params
        assert params[0].name == "x"
        assert params[0].description == "The x value."

    def test_unmatched_docstring_entry_never_invents_a_param(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        names = [p.name for p in symbol.signatures[0].params]
        assert names == ["x"]  # "missing" documented but not introspected

    def test_raises_and_returns_description(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        sig = symbol.signatures[0]
        assert sig.raises[0].type == "ValueError"
        assert sig.raises[0].condition == "If x is negative."
        assert sig.returns_description == "The rendered result."

    def test_examples_populated(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        examples = symbol.semantics.examples
        assert len(examples) == 1
        assert ">>> do_thing(1)" in examples[0].code

    def test_summary_and_description_unchanged(self):
        scanned = _scanned_documented_function()
        _, symbol = _convert_symbol(scanned)
        # description keeps the scanner's full post-summary remainder —
        # information the parser drops (mid-doc Note sections) must survive.
        assert symbol.semantics.summary == scanned.summary
        assert symbol.semantics.description == scanned.description

    def test_introspection_wins_on_type(self):
        _, symbol = _convert_symbol(_scanned_documented_function())
        # docstring says "x (int)" but the introspected type is the source
        # of truth; docstring only contributes the description text
        assert symbol.signatures[0].params[0].type == "int"

    def test_no_docstring_falls_back_to_today(self):
        scanned = _scanned_documented_function()
        scanned.docstring = None
        _, symbol = _convert_symbol(scanned)
        sig = symbol.signatures[0]
        assert sig.raises is None
        assert sig.returns_description is None
        assert symbol.semantics.examples is None
        assert sig.params[0].description is None

    def test_fail_open_on_parser_exception(self, monkeypatch):
        import lcp.docstrings as docstrings_mod

        def boom(text):
            raise RuntimeError("parser exploded")

        monkeypatch.setattr(docstrings_mod, "_parse", boom)
        scanned = _scanned_documented_function()
        _, symbol = _convert_symbol(scanned)
        assert symbol.semantics.summary == scanned.summary
        assert symbol.semantics.description == scanned.description
        assert symbol.signatures[0].raises is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_generator.py::TestStructuredDocstrings -v`
Expected: FAIL — `ScannedSymbol` accepts `docstring` (Task 4 landed) but descriptions/raises/examples are `None`.

- [ ] **Step 3: Implement the wiring**

In `src/lcp/generator.py`:

1. Extend imports: add `RaisesEntry` and `Example` to the `from .models import (...)` list, and add `from .docstrings import DocstringExtras, extract_structured`.

2. `_convert_param` gains an optional extras argument (existing behavior when absent):

```python
def _convert_param(param: ScannedParam, extras: DocstringExtras | None = None) -> Param:
```

and its final return changes the `description` line to:

```python
    description = param.description
    if description is None and extras is not None:
        description = extras.param_descriptions.get(param.name)

    return Param(
        name=param.name,
        type=param.type_hint or "Any",
        required=not param.has_default,
        default=default_value if param.has_default else None,
        variadic=param.is_variadic,
        kind=_param_kind_to_lcp(param.kind),
        description=description,
    )
```

3. `_convert_signature` gains the same optional argument and fills the new fields:

```python
def _convert_signature(
    sig: ScannedSignature, extras: DocstringExtras | None = None
) -> Signature:
    """Convert a scanned signature to LCP Signature.

    Docstring extras only decorate introspected params (matched by name);
    an unmatched docstring entry never invents a Param.
    """
    params = [_convert_param(p, extras) for p in sig.params] if sig.params else None

    raises = None
    returns_description = None
    if extras is not None:
        if extras.raises:
            raises = [
                RaisesEntry(type=exc_type, condition=condition)
                for exc_type, condition in extras.raises
            ]
        returns_description = extras.returns_description

    return Signature(
        async_=sig.is_async,
        params=params,
        returns=sig.return_type,
        returns_description=returns_description,
        raises=raises,
    )
```

4. `_convert_symbol` parses once per symbol (fail-open lives inside `extract_structured`):

```python
def _convert_symbol(scanned: ScannedSymbol) -> tuple[str, Symbol]:
    """Convert a scanned symbol to LCP Symbol with its ID."""
    symbol_id = _build_symbol_id(scanned)

    extras = extract_structured(scanned.docstring)

    examples = None
    if extras is not None and extras.examples:
        examples = [
            Example(code=code, description=description)
            for code, description in extras.examples
        ]

    # Build semantics — summary and description are the scanner's values,
    # unchanged: the raw remainder must survive even when parsing succeeds.
    semantics = Semantics(
        summary=scanned.summary or f"{scanned.kind.capitalize()} {scanned.name}",
        description=scanned.description,
        examples=examples,
    )

    # Build signatures for callables
    signatures = None
    if scanned.signature and scanned.kind in ("function", "method", "class"):
        signatures = [_convert_signature(scanned.signature, extras)]
    ...
```

(the rest of `_convert_symbol` — `alias_ids`, `Symbol(...)`, return — is unchanged).

- [ ] **Step 4: Run generator + full suite**

Run: `.venv/bin/python -m pytest tests/test_generator.py tests/test_validator.py tests/test_cli.py -v`
Expected: all PASS (pre-existing generator tests confirm the no-docstring path is unchanged).

- [ ] **Step 5: Commit**

```
UPD: Generator fills Param.description, raises, returns and examples

extract_structured() runs once per symbol at generate time; docstring
params merge with introspected params by name (introspection wins on
existence and type, unmatched entries never invent a Param), and
semantics.summary/description stay byte-identical to the previous
output so no information is lost on any path.
```

---

### Task 7: `get_symbol` — structured fields in responses + examples-aware byte budget

**Files:**
- Modify: `src/lcp/mcp_server.py` (`_symbol_detail`, ~lines 823-833)
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: populated `Symbol` models (Task 6). `_symbol_detail` already emits them via `symbol.model_dump(exclude_none=True)` — no new plumbing for the fields themselves.
- Produces: response keys `semantics.examples`, `signatures[0].raises`, `signatures[0].returns_description`, `params[].description`; new truncation markers `examples_truncated: true` (and examples dropped oldest-last) when the 25k cap would be exceeded, applied **before** the existing description truncation.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mcp_server.py`, following the file's existing pattern for building an `LCPIndex` from a hand-made `LCPDocument` (reuse the existing document/index fixture helpers already used by the `_symbol_detail`/get_symbol tests):

```python
def _documented_symbol():
    return Symbol(
        kind=SymbolKind.FUNCTION,
        module="pkg",
        signatures=[
            Signature(
                params=[
                    Param(name="x", type="int", description="The x value.")
                ],
                returns="str",
                returns_description="The rendered result.",
                raises=[RaisesEntry(type="ValueError", condition="If x < 0.")],
            )
        ],
        semantics=Semantics(
            summary="Do a thing.",
            examples=[
                Example(code=">>> do_thing(1)\n'ok'", description="Basic."),
                Example(code=">>> do_thing(2)\n'ok2'"),
            ],
        ),
    )


class TestStructuredFieldsInGetSymbol:
    def test_structured_fields_exposed(self):
        # build a one-symbol document/index exactly like the neighboring
        # tests do, with id "pkg:do_thing" -> _documented_symbol()
        detail = _symbol_detail(index, "pkg:do_thing", symbol, 25_000)
        sig = detail["signatures"][0]
        assert sig["params"][0]["description"] == "The x value."
        assert sig["returns_description"] == "The rendered result."
        assert sig["raises"] == [
            {"type": "ValueError", "condition": "If x < 0."}
        ]
        assert len(detail["semantics"]["examples"]) == 2

    def test_examples_truncated_before_description(self):
        # tiny budget: examples must shrink (with the marker) before the
        # description is sacrificed
        symbol = _documented_symbol()
        symbol.semantics.description = "prose " * 50
        big = Example(code=">>> big()\n" + "x" * 2000)
        symbol.semantics.examples = [symbol.semantics.examples[0], big]
        detail = _symbol_detail(index, "pkg:do_thing", symbol, 1_200)
        assert detail.get("examples_truncated") is True
        assert len(json.dumps(detail, default=str)) <= 1_200
```

Adapt fixture/builder names to what the file actually uses (there are existing direct `_symbol_detail` tests from Phase 2/3 — copy their setup verbatim; do not invent a new fixture style).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -v -k "StructuredFields or examples_truncated"`
Expected: first test PASSES already if model_dump flows through (fine — keep it as a shape lock); the truncation test FAILS (no `examples_truncated`, or over budget).

- [ ] **Step 3: Implement examples-aware budgeting**

In `_symbol_detail` (`src/lcp/mcp_server.py`), immediately **before** the existing description-truncation block (`slack = 400` ... ), insert:

```python
    # Enforce the byte budget on the entry itself. Cheapest sacrifice first:
    # drop trailing examples, then truncate the description as a last resort.
    slack = 400  # headroom for the truncation-marker fields added below
    body_size = len(json.dumps(result, default=str))
    examples = result.get("semantics", {}).get("examples")
    if body_size + slack > max_bytes and examples:
        examples_size = len(json.dumps(examples, default=str))
        example_budget = max(0, max_bytes - (body_size - examples_size) - slack)
        kept_examples, examples_truncated = _fit_list(examples, example_budget)
        if examples_truncated:
            if kept_examples:
                result["semantics"]["examples"] = kept_examples
            else:
                result["semantics"].pop("examples", None)
            result["examples_truncated"] = True
        body_size = len(json.dumps(result, default=str))
```

and change the existing block to reuse that `body_size` (remove its duplicate `slack = 400` / `body_size = ...` lines):

```python
    description = result.get("semantics", {}).get("description")
    if body_size + slack > max_bytes and description:
        overshoot = body_size + slack - max_bytes
        kept = max(0, len(description) - overshoot)
        result["semantics"]["description"] = description[:kept]
        result["description_truncated"] = True
        body_size = len(json.dumps(result, default=str))
```

- [ ] **Step 4: Run the MCP suite**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -v`
Expected: all PASS (existing truncation tests unchanged).

- [ ] **Step 5: Commit**

```
UPD: Byte-budget examples in get_symbol before description truncation

Structured fields flow into responses via model_dump; docstring examples
can be large (polars-scale Examples sections), so _symbol_detail now
drops trailing examples under the 25k cap (examples_truncated marker)
before sacrificing the description, mirroring the members budget.
```

---

### Task 8: exit-criteria measurements (real libraries)

**Files:**
- Create: `/private/tmp/.../scratchpad/postmeasure.py` (scratchpad only — NOT committed)
- No src changes expected; numbers go into the roadmap log (Task 11) and the eval `analysis.md` (Task 10).

**Interfaces:**
- Consumes: the full pipeline from Tasks 1–7.
- Produces: three recorded numbers — (a) % documented params with `description` (target ≥90%), (b) manifest gzip growth vs the baselines in the header table (threshold ≤2×), (c) polars `DataFrame` `get_symbol` response size vs the 25,000-byte cap.

- [ ] **Step 1: Write the measurement script**

Scratchpad `postmeasure.py`:

```python
import gzip, json
from lcp.scanner import scan_package
from lcp.generator import generate_lcp
from lcp.docstrings import extract_structured
from lcp.mcp_server import LCPIndex, _symbol_detail, DEFAULT_MAX_RESPONSE_BYTES

BASELINE_GZIP = {"fastmcp": 287_528, "polars": 640_346, "click": 51_412}

def walk(symbols):
    for s in symbols:
        yield s
        yield from walk(s.members)

for pkg in ("fastmcp", "polars", "click"):
    scanned = scan_package(pkg)
    doc = generate_lcp(scanned)
    raw = doc.model_dump_json(exclude_none=True, by_alias=True).encode()
    gz = len(gzip.compress(raw))
    documented = matched = 0
    for s in walk(scanned.symbols):
        if not s.signature:
            continue
        extras = extract_structured(s.docstring)
        if not extras:
            continue
        intro = {p.name for p in s.signature.params if p.name not in ("self", "cls")}
        documented += len(extras.param_descriptions)
        matched += len(intro & set(extras.param_descriptions))
    pct = 100 * matched / documented if documented else 0.0
    growth = gz / BASELINE_GZIP[pkg]
    print(f"{pkg}: documented-params-with-description {pct:.1f}% "
          f"({matched}/{documented})  gzip {gz:,} B  growth x{growth:.2f}")
    if pkg == "polars":
        index = LCPIndex(doc)
        sid = next(i for i in index.symbols_by_id if i.endswith(":DataFrame"))
        detail = _symbol_detail(index, sid, index.symbols_by_id[sid],
                                DEFAULT_MAX_RESPONSE_BYTES)
        size = len(json.dumps(detail, default=str))
        print(f"polars DataFrame get_symbol: {size:,} B "
              f"(cap {DEFAULT_MAX_RESPONSE_BYTES:,}) "
              f"examples_truncated={detail.get('examples_truncated', False)} "
              f"description_truncated={detail.get('description_truncated', False)}")
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python <scratchpad>/postmeasure.py`
Expected:
- all three libraries ≥90% documented-params-with-description (pre-measured 93–98% match rate);
- gzip growth ×≤2.0 for each library;
- polars DataFrame detail ≤25,000 B (truncation markers acceptable).

- [ ] **Step 3: Decision gate**

- If growth >2× on any library: STOP and reopen the inline-vs-lazy question for `get_symbol` with the user (roadmap exit criterion) before proceeding.
- If <90%: investigate the top unmatched names (renamed params are expected; a parser/normalization bug is not) before proceeding.
- Record the numbers verbatim for Task 10's `analysis.md` and Task 11's roadmap log. No commit (scratchpad only).

---

### Task 9: docs alignment (same phase, `lcp-writing-documentation` skill)

**Files (verify each against the skill's area conventions):**
- Modify: `docs/spec/schema.md` (document `returns_description` next to the other signature fields)
- Modify: `docs/spec/index.md` (structured docstring fields now populated; freeze note)
- Modify: `docs/architecture/manifest/architecture.md` (generator now parses docstrings fail-open; description remainder rule)
- Modify: `docs/architecture/mcp_server/architecture.md` (examples truncation in the response budget) — only if that page describes the budget mechanics
- Modify: `docs/guides/mcp-server.md` (get_symbol response now carries param descriptions, raises, returns_description, examples + `examples_truncated`)
- Modify: `plugin/lcp/skills/lcp-universal/SKILL.md`, `plugin/lcp/skills/lcp-usage/SKILL.md` (responses now include structured docs/examples — keep the additions one-line each, matching Phase 3's alias additions)
- `docs/assets/schema.json` already updated in Task 5.

- [ ] **Step 1: Invoke the `lcp-writing-documentation` skill** and apply its conventions to the files above (architecture = conceptual, no code snippets; guides = user-facing with examples; API reference = touch docstrings only, which Tasks 2–7 already wrote in Google style).

- [ ] **Step 2: Build strict**

Run: `.venv/bin/python -m mkdocs build --strict` (install `.[docs]` extras first if missing).
Expected: clean build, no warnings.

- [ ] **Step 3: Commit**

```
DOC: Document structured docstring fields across spec, guides and skills
```

---

### Task 10: end-of-phase eval run (lcp-skill arm, 8 F1 cases)

**Files:**
- Create: `evals/results/2026-07-07-phase4-docstrings-skill/` (meta.json, report.md, analysis.md, summary.json, runs/)

**Interfaces:**
- Consumes: the phase branch checked out (editable install in `evals/.venv` serves THIS branch).
- Produces: recorded eval vs `evals/results/2026-07-06-phase3-aliases-skill` (same verifier — no rescore, no harness co-fix expected this time).

- [ ] **Step 1: Pre-flight (all four, in order)**

```bash
git branch --show-current        # MUST print roadmap/phase-4-structured-docstrings
evals/.venv/bin/pip install docstring_parser   # manual: do NOT pip install -e ".[dev]" here (fastmcp 2.14.4 pinned)
evals/.venv/bin/python -c "import fastmcp; print(fastmcp.__version__)"  # MUST still print 2.14.4
rm -rf evals/.lcp-cache          # cached manifests lack the new fields
claude --version                 # note the version for meta.json (Phase 3 was 2.1.201)
```

- [ ] **Step 2: Run**

```bash
evals/.venv/bin/python evals/run.py run \
  --out evals/results/2026-07-07-phase4-docstrings-skill \
  --arms lcp-skill --reps 3 --model claude-haiku-4-5-20251001
```

Expected: 24 runs (8 cases × 3 reps), summary.json + report.md produced by the runner.

- [ ] **Step 3: Author meta.json + analysis.md**

`meta.json` mirrors the Phase 3 file's shape (experiment, date, claude_version, model, lcp_commit, arm, cases, reps, reference, note). Set `reference` to `evals/results/2026-07-06-phase3-aliases-skill (same verifier — direct comparison)`. In `note`, record: cache cleared, docstring_parser installed manually in evals/.venv, CLI version drift vs 2.1.201 if any. `analysis.md` compares pass counts and misuse/run vs Phase 3 (16/24, 0.33) and includes the Task 8 measurement numbers.

- [ ] **Step 4: Commit**

```
UPD: Record Phase 4 structured-docstrings eval (lcp-skill re-run)
```

(plus `git add -f` is not needed for `evals/` — only `docs/superpowers` needs it.)

---

### Task 11: close the phase

**Files:**
- Modify: `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md` (Phase 4 **Status** line + **Eval results log** + freeze reached)
- This plan file: check off completed tasks.

- [ ] **Step 1: Full-suite gate**

Run: `.venv/bin/python -m pytest -q`
Expected: no NEW failures vs the Task 1 Step 3 baseline (pre-existing `--version` pyenv-shim env failures only).

- [ ] **Step 2: Update the roadmap**

- Phase 4 Status → `done (2026-07-07) — PR #NN`, one-line summary including: exit-criteria numbers (≥90% check result, gzip growth, polars DataFrame size), de-scope NOT exercised (examples shipped) or exercised (if Task 3 was cut).
- Eval results log: append the Phase 4 entry with the comparison vs Phase 3.
- Note that the manifest format is now **frozen** for Phase 7 registry population.

- [ ] **Step 3: Commit (git add -f for docs/superpowers) and push**

```
UPD: Record Phase 4 eval results and close the phase in the roadmap
```

- [ ] **Step 4: Open the PR**

Base `roadmap/agentic-improvements`, title `MRG: Structured docstrings + examples (Phase 4)` (MRG, not CODE). Body: summary, exit-criteria table, eval comparison, freeze note. **No co-author / session links** (public repo).

---

## Self-review notes

- Spec coverage: D11 fields (Param.description ✓ T6, raises ✓ T2/T6, returns description ✓ T5/T6, examples ✓ T3/T6), fail-open ✓ T2/T6, generator-level parsing ✓ T4 (capture-only scanner), merge-by-name/never-invent ✓ T6, get_symbol + polars size check ✓ T7/T8, pyproject core dep separate DEP commit ✓ T1, exit criteria pre-measured (X=90%) ✓ header/T8, gzip 2× gate ✓ T8, eval re-run ✓ T10, docs alignment ✓ T9, freeze note ✓ T11, de-scope line = Task 3 severable ✓.
- Type consistency: `DocstringExtras.param_descriptions/raises/returns_description/examples` names used identically in Tasks 2, 3, 6, 8; `extract_structured` signature identical everywhere; `Signature.returns_description` plain field name in model, schema, tests and generator.
- Known adaptation points (flagged in-task, not placeholders): test_validator/test_mcp_server fixtures must copy the neighboring Phase 2/3 test setup style rather than invent new fixtures.
