# JSON Schema

The canonical machine-readable schema for LCP v1 is published in this repository at [`schema.json`](../assets/schema.json){ download="lcp-v1.schema.json" }.

Use it to validate any `.lcp.json` document with any JSON Schema validator. The Python SDK runs this validation automatically as part of `lcp scan` and via the standalone [`lcp validate`](../cli.md#lcp-validate) command.

## Top-level fields

The root object requires `manifest` and `symbols`. The two optional sections extend the document with historical and traceability information. Extension keys (`x-*`) are permitted at every level.

| Field | Type | Required | Description |
|---|---|---|---|
| `manifest` | object | yes | Library identity and metadata envelope. |
| `symbols` | `object<string, symbol>` | yes | Map of Symbol ID → symbol object; the core of the document. |
| `deprecations` | `object<string, deprecation>` \| null | no | Map of Symbol ID → deprecation record for removed or deprecated symbols. |
| `detailed_index` | `object<string, object>` \| null | no | Map of Symbol ID → source artifact links for IDE and traceability tooling. |

### `manifest` sub-fields

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | Must be `"1.0"` for LCP v1 documents. |
| `library` | object | yes | Core library identity: `name`, `version`, `language`. |
| `library.name` | string | yes | Canonical library name. |
| `library.version` | string | yes | Version string in `MAJOR.MINOR.PATCH` (semver-ish) form. |
| `library.language` | string | yes | Primary implementation language (e.g., `"python"`). |
| `library.runtime_language` | string \| null | no | Runtime language when different from implementation language. |
| `library.bindings` | string \| null | no | Binding type or target ecosystem. |
| `compatibility` | object \| null | no | Runtime and platform constraints (`python`, `node`, `platforms`). |
| `distribution` | string \| null | no | Package registry: `pypi`, `npm`, `cargo`, `maven`, `nuget`, or `other`. |
| `license` | string \| null | no | SPDX identifier or free-text license name. |
| `changelog` | object \| null | no | Changelog location: `url` (URI) and `format` (string). |
| `generation` | object \| null | no | Generator metadata: `tool`, `version`, `date` (ISO 8601). |
| `symbol_resolution` | string | no | `"fully-qualified"` (default) or `"module-relative"`. |

## The symbol object

Each value in the `symbols` map is a **symbol object** defined under `$defs/symbol` in the schema. Only `kind` and `semantics` are required; all other fields are optional and can be omitted when the information is not available or not applicable.

The `semantics` sub-object is itself required to contain at least a `summary` string — a single concise sentence describing what the symbol does. This is the minimum viable symbol that passes validation.

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | string | yes | One of `function`, `class`, `method`, `attribute`, `module`, `constant`. |
| `semantics` | object | yes | Meaning of the symbol; must contain at least `summary`. |
| `semantics.summary` | string | yes | One-sentence description, suitable for hover docs or autocomplete. |
| `semantics.description` | string \| null | no | Extended prose; MAY use Markdown. |
| `semantics.examples` | `array<{code, description?}>` \| null | no | Usage examples with required `code` field. |
| `module` | string \| null | no | Dotted module path where the symbol is defined. |
| `signatures` | `array<signature>` \| null | no | Callable signatures (one per overload). Functions/methods typically have one entry. |
| `effects` | object \| null | no | Observable side-effects: `categories`, `idempotent`, `thread_safe`, `deterministic`. |
| `stability` | object \| null | no | API stability: `level` (`experimental`/`stable`/`deprecated`), `since`, `notes`, `tracking_issue`. |
| `requires` | `array<string>` \| null | no | Symbol IDs that must be present for this symbol to function. |

### `signature` sub-fields

Each entry in `signatures` describes one callable form:

| Field | Type | Description |
|---|---|---|
| `when` | string \| null | Condition under which this signature applies (for overloads). |
| `async` | boolean | Whether the call is asynchronous. Defaults to `false`. |
| `params` | `array<param>` \| null | Ordered parameter list. |
| `returns` | type_ref | Return type. A plain string or a structured type object. |
| `raises` | `array<{type, condition?}>` \| null | Exceptions the callable may raise. |

## Validating a document

Validate any LCP file with the Python SDK:

```bash
lcp validate my-library.lcp.json
```

For non-Python tools, use any JSON Schema 2020-12 validator. For example with [Ajv](https://ajv.js.org/) (Node):

```bash
ajv validate -s lcp-v1.schema.json -d my-library.lcp.json
```

Or [`check-jsonschema`](https://github.com/python-jsonschema/check-jsonschema) (cross-language):

```bash
check-jsonschema --schemafile lcp-v1.schema.json my-library.lcp.json
```

## See also

- [LCP v1 spec](index.md) — the prose specification.
- [Examples](examples.md) — minimal sample documents.
