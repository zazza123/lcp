"""Rot guard: fenced JSON examples in docs/ must validate against the LCP schema.

Blocks that are not standalone JSON (illustrative fragments like
``"symbols": { ... }``) are skipped; blocks that parse are validated when
they are a full LCP document (top-level ``manifest``) or a symbols map
(every value is an object carrying ``kind``). Other parseable JSON (MCP
client configs, error-shape examples) is out of scope and skipped.
"""

import json
import re
from pathlib import Path

import pytest

from lcp.validator import validate_dict

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
EXCLUDED_TOP_DIRS = {"api", "superpowers"}
FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)

MINIMAL_MANIFEST = {
    "schema_version": "1.0",
    "library": {"name": "docs-example", "version": "1.0.0", "language": "python"},
}
SYMBOL_KINDS = {"module", "function", "class", "method", "attribute", "constant"}


def _iter_json_blocks():
    for path in sorted(DOCS_DIR.rglob("*.md")):
        rel = path.relative_to(DOCS_DIR)
        if rel.parts[0] in EXCLUDED_TOP_DIRS:
            continue
        for i, match in enumerate(FENCE_RE.finditer(path.read_text())):
            yield f"{rel}#{i}", match.group(1)


def _as_lcp_document(block: str):
    """Return a full LCP document dict for validatable blocks, else None."""
    try:
        data = json.loads(block)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data:
        return None
    if "manifest" in data:
        return data
    if data.get("kind") in SYMBOL_KINDS:
        # A bare symbol object, shown without its ID key. (type_ref objects
        # also carry "kind", but with values like "array"/"union" — excluded.)
        return {"manifest": MINIMAL_MANIFEST, "symbols": {"example:symbol": data}}
    if all(isinstance(v, dict) and v.get("kind") in SYMBOL_KINDS for v in data.values()):
        return {"manifest": MINIMAL_MANIFEST, "symbols": data}
    return None


BLOCKS = list(_iter_json_blocks())
VALIDATABLE = [
    (block_id, doc)
    for block_id, block in BLOCKS
    if (doc := _as_lcp_document(block)) is not None
]


@pytest.mark.parametrize(
    ("block_id", "document"),
    VALIDATABLE,
    ids=[block_id for block_id, _ in VALIDATABLE],
)
def test_docs_json_examples_validate(block_id, document):
    errors = validate_dict(document)
    assert not errors, f"{block_id} does not validate: {errors}"


def test_minimum_validatable_examples():
    """The guard must keep matching real examples; if this drops below the
    floor, the extraction heuristic broke or examples were removed."""
    assert len(VALIDATABLE) >= 3, [b for b, _ in VALIDATABLE]
