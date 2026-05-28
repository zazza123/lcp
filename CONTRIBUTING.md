# Contributing to `lcp`

Thanks for your interest in improving the Library Context Protocol SDK. This
guide covers everything you need to set up a development environment, run the
test suite, and open a pull request.

## Development setup

`lcp` targets Python 3.10+ and uses a `src/` layout.

```bash
# Clone and enter the repo
git clone https://github.com/zazza123/lcp.git
cd lcp

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate            # macOS / Linux
# .venv\Scripts\activate             # Windows

# Install the package in editable mode with dev + AI extras
pip install -e ".[ai,dev]"
```

The `dev` extra pulls in `pytest`, `pytest-cov`, `pytest-asyncio`, and `ruff`.
The `ai` extra pulls in `openai` and `anthropic`, needed for the AI docstring
generation module.

## Running tests

```bash
# Full test suite
pytest

# A single file / class / test
pytest tests/test_scanner.py
pytest tests/test_scanner.py::TestScanClass
pytest tests/test_scanner.py::TestScanClass::test_scan_class

# Verbose
pytest -v
```

## Linting

```bash
ruff check src/lcp tests
```

Both `pytest` and `ruff check` must pass before a PR can be merged.

## Project layout

The codebase follows a **scan → generate → validate** pipeline. The key
modules under `src/lcp/`:

| Module | Purpose |
|--------|---------|
| `scanner.py` | Python introspection (`inspect` + `ast`) |
| `generator.py` | Scanned data → Pydantic `LCPDocument` |
| `validator.py` | JSON Schema validation against `schema.json` |
| `mcp_server.py` | FastMCP server exposing LCP manifests |
| `coverage.py` | Documentation coverage analysis |
| `ai/` | Optional AI docstring generation (`lcp[ai]`) |
| `cli.py` | Click-based CLI |
| `models.py` | Pydantic models matching the LCP v1 spec |

The Claude Code plugin lives under `plugin/lcp/`. See `CLAUDE.md` for a more
detailed map.

## Commit message convention

Commit messages use a three-letter action code prefix in **uppercase**, a
colon, and a short imperative title:

```
ADD: scanner support for protocol classes
UPD: docgen prompt phrasing for L1 classes
FIX: validator rejecting valid enum values
DOC: clarify pipeline diagram in README
REF: extract shared traversal helper from scanner
TST: add coverage tests for namespace packages
SEC: tighten input validation in MCP server
DEL: remove dead code path in legacy generator
```

Common codes: `ADD`, `UPD`, `FIX`, `DOC`, `REF`, `TST`, `SEC`, `DEL`.

Keep the title under ~70 characters. Use the body for the *why*, not the
*what* — the diff already shows what changed.

## Pull request process

1. **One logical change per PR.** Smaller PRs review faster and are easier to
   revert if needed.
2. **Branch from `main`** and keep the branch focused.
3. **Tests are required** for new behaviour and for any bug fix that has a
   reproducer.
4. **CI must be green.** Run `ruff check src/lcp tests` and `pytest` locally
   before pushing.
5. **Update documentation** in `docs/`, `README.md`, or docstrings when user-
   visible behaviour changes.
6. **Squash merge** is the default. Make sure the final commit message
   follows the convention above.
7. **Reviews are required** before merge.

If you are not sure whether an idea fits the project, open a discussion or a
feature request issue first rather than building a large PR speculatively.

## Reporting bugs and proposing features

Use the structured issue forms — they prefill the right fields and apply
labels for triage:

- **Bug report**: [`New issue → Bug report`](https://github.com/zazza123/lcp/issues/new?template=bug_report.yml)
- **Feature request**: [`New issue → Feature request`](https://github.com/zazza123/lcp/issues/new?template=feature_request.yml)
- **Usage questions / design discussion**: use
  [GitHub Discussions](https://github.com/zazza123/lcp/discussions).

Please do not file blank issues — they will be closed and redirected to the
appropriate template.

## Reporting security vulnerabilities

**Do not open a public issue for security problems.** See
[`SECURITY.md`](SECURITY.md) for the private disclosure process (GitHub
Security Advisories, or email `andrea.za94@gmail.com`).

## Code of Conduct

Participation in this project is governed by the
[Code of Conduct](CODE_OF_CONDUCT.md), adapted from the Contributor
Covenant v2.1. By contributing, you agree to uphold it.
