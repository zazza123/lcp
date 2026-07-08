# Phase 7 — Registry: CI Verification + Pre-population — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The registry verifies manifest submissions automatically in CI (green check replaces manual review) and ships pre-built manifests for the top-100 PyPI libraries, so `serve-all --registry` has answers on day one.

**Architecture:** Work spans two repos. In the **SDK repo** (`~/Projects/lcp/lcp`, branch `roadmap/phase-7-registry`): idempotent `publish.py` upserts and version-mismatch honesty in `resolve_library`. In the **registry repo** (`~/Projects/lcp/lcp-registry`, clone at that path, PRs to `main`): a new `verify-manifests.yml` workflow (layout/schema checks + isolated regenerate-and-compare), a batch `populate.py` script run locally by the owner, then the actual population PRs.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, `gh` CLI, existing lcp modules (`subprocess_scan`, `naming`, `validator`, `models`).

## Global Constraints

- SDK suite must be green at start and end: **570+ passed, 0 failed** (`.venv/bin/python -m pytest -q`); plugin shell tests too (`bash tests/plugin/run_all.sh`).
- Lint before every push: `.venv/bin/ruff check src/lcp` and `.venv/bin/ruff check tests`.
- Commits via `git-commit-convention` skill; **no co-author/session links** (both repos public).
- Docs via `lcp-writing-documentation` skill; `mkdocs build --strict` clean.
- No new runtime deps in the SDK. LCP schema stays `"1.0"`; all additions additive.
- Registry repo: **never push to `main`** — branch + PR, wait `gh pr checks --watch`, resolve review/bot comments in session.
- Do NOT touch `evals/.venv`. No eval-harness run required for Phase 7.
- `docs/superpowers/` files are committed with `git add -f` (SDK repo).
- SDK PR title prefix `MRG:` (not `CODE:`), base `roadmap/agentic-improvements`.

---

## Settled Open Decisions

**D1 — Batch pre-population script lives in the registry repo (`.github/lcp/populate.py`) and runs LOCALLY on the owner's machine, not in Actions and not via `publish.py`.**
Motivation: the registry repo already owns manifest-generation ops (`update_manifests.py`, `sync_latest.py`, `packages.yaml`, weekly workflow) — registry operations tooling belongs next to it, and `populate.py` reuses `sync_latest.compute_latest` directly by sibling import. Running locally (100 venvs, multi-GB installs like torch) avoids Actions disk/time limits and is resumable. Deviation from the roadmap's "via the existing publish.py flow" is deliberate: `publish.py` is the *community* path (fork + Contents-API + one PR per package = 100 PRs, base64 uploads, rate limits); as repo owner with a local clone, direct branches + batched PRs (~20 packages/PR) are far cheaper, and trust comes from the new verify CI gating every PR, not from the submission channel. `publish.py` still gets the idempotence fix (Task 1) because community re-runs need it regardless.

**D2 — `latest.json` is maintained by the existing machinery, extended, not replaced.**
The registry already solves this two ways: `sync_latest.py` runs on every `manifests/**` PR (`validate-manifests.yml`) and rewrites `latest.json` from files on disk, committing back to the PR branch; the weekly updater writes it directly. Decision: (a) `populate.py` writes `latest.json` itself using `sync_latest.compute_latest` (same code, no drift) so batch PRs arrive already consistent; (b) the new verify workflow **checks** `latest.json` consistency and fails red if the pointer is missing/stale — necessary because the sync job's auto-push cannot work on fork PRs (read-only `GITHUB_TOKEN`), so community fork PRs would otherwise land with silently-broken pointers. Regen of already-published versions never moves `latest.json`.

**D3 — CI comparison tolerance policy.**
Hard gates (always fail): gzip integrity, JSON parse, `lcp` schema validation, path layout (`manifests/{lang}/{letter}/{slug}/{version}.lcp.json.gz`, `letter == slug[0]`, slug already PEP-503 normalized, manifest `library.version` == filename version, `library.language` == `{lang}` folder), `latest.json` consistency. Regenerate-and-compare gate: install `{slug}=={version}` from PyPI in a fresh venv, scan `library.name` (the import name) with **pinned lcp**, then PASS iff (1) symbol-ID symmetric difference ≤ **2% of the union** (env-dependent symbols: platform-conditional classes, optional extras, import-time `__all__`) and (2) **every** spot-checked signature matches exactly — deterministic sample of up to 50 common symbols (sorted ids, every k-th), comparing `signature` + `kind`. Signature mismatches are never tolerated (that is the exit-criterion attack). Escape hatch for legitimately divergent packages: `.github/lcp/verify-overrides.yaml` with per-package `symbol_tolerance` and `skip_signature_ids`, both requiring PR review to change. Policy documented in the registry README.

**D4 — Population target: top 100** (de-scoping rule; 500 only if the pipeline later proves cheap — it will not be re-decided in this session). Source: hugovk `top-pypi-packages` 30-day dump, minus an explicit exclusion list (packaging infra, stubs, CLI-only meta packages), force-including `polars` (exit criterion) — frozen into a reviewable `.github/lcp/population.yaml`. The 10 pre-freeze manifests (6 libraries) are regenerated at their **same versions** in a dedicated regen batch.

**D5 — Version-mismatch honesty (SDK):** in `resolve_library`, whenever `source` is `"cache"` or `"registry"` and the resolved manifest version differs from the *installed* version (including "not installed at all" → `installed_version: null`), the response carries top-level `"version_mismatch": true` + `"installed_version"` + `"resolved_version"`. The existing `warning` block for an explicitly *requested* version mismatch stays untouched (back-compat with Phase 2 shape). `source == "scan"` never flags (a live scan is by definition the installed version).

**D6 — CI security posture (the critical caveat):** the regenerate job executes arbitrary code (`pip install` of attacker-chosen packages). Mitigations, stated in the workflow header comment and SECURITY.md: trigger is `pull_request` (NEVER `pull_request_target`) so fork PRs get a read-only token and **no secrets**; workflow-level `permissions: contents: read`; GitHub-hosted ephemeral runners (fresh VM per job, destroyed after); no repo credentials in job env; documented egress: `pypi.org`, `files.pythonhosted.org` (package install), `github.com` (pinned lcp install + checkout). Signing/attestation is out of scope and documented as a known limitation.

**D7 — lcp version pinning:** PyPI's `lcp` is 1.0.2 (pre-Phase-2/3/4) — anything that regenerates manifests MUST NOT use it or manifests lose the frozen Phase-4 structured fields. `.github/lcp/requirements.txt` pins `lcp @ git+https://github.com/zazza123/lcp@98efe82…` (full 40-char SHA of the current `roadmap/agentic-improvements` head; generation code frozen since Phase 4, Phase 7 SDK changes don't touch scanner/generator). The verify workflow, the weekly updater, and local `populate.py` runs all install from this same file. Bump policy documented: the pin moves only when the SDK intentionally changes manifest output, which implies regenerating the registry.

**Registry path-vs-import naming rule (consequence of D3, made explicit):** the folder slug is the **PyPI distribution name** normalized (`lcp.naming.normalize_package_name`) — that is what agents pass to `resolve_library` and what `_fetch_from_registry` slugs. The manifest's `library.name` is the **import name** and may differ (`python-dateutil` folder / `dateutil` import). CI installs by folder slug and scans by `library.name`. Known limitation (documented, not fixed here): `lcp publish` derives the folder from `library.name`, which is wrong for dist≠import packages like `beautifulsoup4`/`bs4`; `populate.py` is unaffected because it keys folders by dist name from the population list.

---

## File Structure

**SDK repo (`/Users/andreazanini/Projects/lcp/lcp`):**
- Modify `src/lcp/publish.py` — `_create_branch` (tolerate/reset existing branch), `_upload_manifest` (sha upsert), `_create_pull_request` (tolerate existing PR).
- Modify `src/lcp/mcp_server.py` — `resolve_library` version-mismatch flag.
- Modify `tests/test_publish.py`, `tests/test_mcp_server.py`.
- Modify `docs/guides/publishing.md`, `docs/guides/mcp-server.md`, `docs/architecture/publish/architecture.md`, `docs/architecture/mcp_server/architecture.md`.
- Modify `docs/superpowers/plans/2026-07-02-agentic-improvements-roadmap.md` (Status).

**Registry repo (`/Users/andreazanini/Projects/lcp/lcp-registry`):**
- Create `.github/lcp/verify_layout.py` — layout/schema/latest checks (fast job, no package install).
- Create `.github/lcp/regen_compare.py` — venv install + rescan + compare (one manifest per call).
- Create `.github/lcp/verify-overrides.yaml` — per-package tolerance overrides (starts empty).
- Create `.github/lcp/population.yaml` + `.github/lcp/populate.py` — batch population.
- Create `.github/workflows/verify-manifests.yml`.
- Modify `.github/lcp/requirements.txt` (lcp git pin), `README.md`, `.github/SECURITY.md`.
- Population output: `manifests/python/**` (~100 packages × 1 version + 10 regen files).

---

## Part A — SDK repo

All Part A work on branch `roadmap/phase-7-registry` (already checked out, base 98efe82).

### Task 1: Idempotent `publish.py` (upsert on re-run)

**Files:**
- Modify: `src/lcp/publish.py:196-233` (`_create_branch`), `:236-274` (`_upload_manifest`), `:328-371` (`_create_pull_request`)
- Test: `tests/test_publish.py`

**Interfaces:**
- Produces: `_create_branch(fork_repo, branch_name, token) -> str` now succeeds when the branch exists (force-resets it to main HEAD); `_upload_manifest(...)` unchanged signature, adds `sha` to the PUT when the file pre-exists; `_create_pull_request(...)` returns the existing open PR dict when GitHub rejects a duplicate.

- [ ] **Step 1: Write the failing tests** — append to the existing classes in `tests/test_publish.py` (they use `@patch("lcp.publish._github_request")`; mirror that style):

```python
# in class TestCreateBranch:
    @patch("lcp.publish._github_request")
    def test_branch_already_exists_is_reset(self, mock_request):
        """Re-running publish for the same (package, version) must not fail."""
        mock_request.side_effect = [
            {"object": {"sha": "base-sha"}},                       # GET ref main
            PublishError("GitHub API error (HTTP 422): Reference already exists"),
            {},                                                    # PATCH force-reset
        ]
        sha = _create_branch("user/lcp-registry", "lcp/add/foo/1.0", "tok")
        assert sha == "base-sha"
        patch_call = mock_request.call_args_list[2]
        assert patch_call.args[0] == "PATCH"
        assert patch_call.args[1].endswith("git/refs/heads/lcp/add/foo/1.0")
        assert patch_call.kwargs["data"] == {"sha": "base-sha", "force": True}

    @patch("lcp.publish._github_request")
    def test_other_create_branch_error_still_raises(self, mock_request):
        mock_request.side_effect = [
            {"object": {"sha": "base-sha"}},
            PublishError("GitHub API error (HTTP 500): boom"),
        ]
        with pytest.raises(PublishError, match="boom"):
            _create_branch("user/lcp-registry", "lcp/add/foo/1.0", "tok")

# in class TestUploadManifest:
    @patch("lcp.publish._github_request")
    def test_existing_file_upserts_with_sha(self, mock_request):
        mock_request.side_effect = [
            {"sha": "old-file-sha"},   # GET contents?ref=branch
            {},                        # PUT
        ]
        _upload_manifest(
            "user/lcp-registry", "lcp/add/foo/1.0",
            "manifests/python/f/foo/1.0.lcp.json.gz", b"data", "tok", "foo", "1.0",
        )
        put_call = mock_request.call_args_list[1]
        assert put_call.args[0] == "PUT"
        assert put_call.kwargs["data"]["sha"] == "old-file-sha"

    @patch("lcp.publish._github_request")
    def test_new_file_puts_without_sha(self, mock_request):
        mock_request.side_effect = [
            PublishError("GitHub API error (HTTP 404): Not Found"),  # GET
            {},                                                      # PUT
        ]
        _upload_manifest(
            "user/lcp-registry", "lcp/add/foo/1.0",
            "manifests/python/f/foo/1.0.lcp.json.gz", b"data", "tok", "foo", "1.0",
        )
        put_call = mock_request.call_args_list[1]
        assert "sha" not in put_call.kwargs["data"]

# in class TestCreatePullRequest:
    @patch("lcp.publish._github_request")
    def test_existing_open_pr_is_returned(self, mock_request):
        mock_request.side_effect = [
            PublishError(
                "GitHub API error (HTTP 422): A pull request already exists "
                "for user:lcp/add/foo/1.0."
            ),
            [{"html_url": "https://github.com/z/r/pull/7", "number": 7}],  # GET list
        ]
        pr = _create_pull_request(
            "zazza123/lcp-registry", "user/lcp-registry", "lcp/add/foo/1.0",
            "foo", "1.0", "python", "body", "tok",
        )
        assert pr["number"] == 7
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_publish.py -q`
Expected: the 5 new tests FAIL (current code raises PublishError / omits sha).

- [ ] **Step 3: Implement.** In `_create_branch`, replace the bare POST with:

```python
    # Create the branch; tolerate a leftover from a previous run by
    # force-resetting it to the current main HEAD (idempotent re-publish).
    try:
        _github_request(
            "POST",
            f"{_GITHUB_API_BASE}/repos/{fork_repo}/git/refs",
            token,
            data={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
    except PublishError as exc:
        if "already exists" not in str(exc).lower():
            raise
        _github_request(
            "PATCH",
            f"{_GITHUB_API_BASE}/repos/{fork_repo}/git/refs/heads/{branch_name}",
            token,
            data={"sha": base_sha, "force": True},
        )

    return base_sha
```

In `_upload_manifest`, before the PUT:

```python
    encoded_content = base64.b64encode(content).decode("ascii")
    url = f"{_GITHUB_API_BASE}/repos/{fork_repo}/contents/{file_path}"

    # Upsert: GitHub rejects a PUT over an existing file unless its blob
    # sha is supplied, so look it up first (404 -> new file).
    existing_sha: str | None = None
    try:
        existing = _github_request("GET", f"{url}?ref={branch_name}", token)
        if isinstance(existing, dict):
            existing_sha = existing.get("sha")
    except PublishError:
        pass  # file does not exist on the branch yet

    data: dict = {
        "message": f"Add {package_name} v{package_version} LCP manifest",
        "content": encoded_content,
        "branch": branch_name,
    }
    if existing_sha:
        data["sha"] = existing_sha
    _github_request("PUT", url, token, data=data)
```

In `_create_pull_request`, wrap the POST:

```python
    try:
        pr_data = _github_request(
            "POST",
            f"{_GITHUB_API_BASE}/repos/{registry_repo}/pulls",
            token,
            data={
                "title": title,
                "body": pr_body,
                "head": f"{fork_owner}:{branch_name}",
                "base": "main",
            },
        )
    except PublishError as exc:
        if "already exists" not in str(exc).lower():
            raise
        # A PR for this head is already open: return it instead of failing.
        existing = _github_request(
            "GET",
            f"{_GITHUB_API_BASE}/repos/{registry_repo}/pulls"
            f"?head={fork_owner}:{branch_name}&state=open",
            token,
        )
        if isinstance(existing, list) and existing:
            return existing[0]
        raise

    return pr_data
```

Also update the `publish_manifest` docstring: add a line "Re-running for the same (package, version) is idempotent: the branch is reset, the file is updated in place, and the existing open PR is reused."

- [ ] **Step 4: Run the full publish tests**

Run: `.venv/bin/python -m pytest tests/test_publish.py -q`
Expected: ALL PASS.

- [ ] **Step 5: Commit** (git-commit-convention skill; e.g. `UPD: Make publish.py idempotent on re-run`).

### Task 2: Version-mismatch honesty in `resolve_library`

**Files:**
- Modify: `src/lcp/mcp_server.py:1197-1226` (result building in `resolve_library`)
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `resolve_library` result gains, when `source in ("cache", "registry")` and installed ≠ resolved: `"version_mismatch": True`, `"installed_version": <str | None>`, `"resolved_version": <str>`.

- [ ] **Step 1: Write the failing tests.** Locate the existing fixture used by `test_version_mismatch_warning` (`universal_server`, tests/test_mcp_server.py:992) and the cache-seeding helpers used around `test_version_pins_cache_lookup` (:367). Add, following the local idiom:

```python
    def test_version_mismatch_flag_when_cache_differs_from_installed(
        self, tmp_path, sample_lcp_file, monkeypatch
    ):
        """_find_any_cached can serve any version; response must be honest."""
        # seed cache with version 9.9.9 while 'installed' reports 1.0.0
        monkeypatch.setattr(
            "lcp.mcp_server._installed_version", lambda name: "1.0.0"
        )
        # (seed the cache the same way the surrounding cache tests do,
        # with the manifest version set to 9.9.9)
        result = tools["resolve_library"](name="samplepkg", version="9.9.9")
        assert result["version_mismatch"] is True
        assert result["installed_version"] == "1.0.0"
        assert result["resolved_version"] == "9.9.9"

    def test_version_mismatch_flag_when_not_installed(self, ...):
        """Registry/cache hit with no local install → flagged, installed None."""
        monkeypatch.setattr(
            "lcp.mcp_server._installed_version", lambda name: None
        )
        # resolve via cache (any version)
        assert result["version_mismatch"] is True
        assert result["installed_version"] is None

    def test_no_mismatch_flag_on_scan_source(self, ...):
        """A live scan is the installed version by definition — never flagged."""
        # resolve with empty cache so source == "scan"
        assert "version_mismatch" not in result

    def test_no_mismatch_flag_when_cache_matches_installed(self, ...):
        # installed == cached version → clean response
        assert "version_mismatch" not in result
```

(The executor must adapt fixture wiring to the real neighbouring tests — the four *behaviors* above are the requirement; keep asserts as written.)

- [ ] **Step 2: Run to verify they fail** — `.venv/bin/python -m pytest tests/test_mcp_server.py -k mismatch -q` → new tests FAIL (`KeyError: 'version_mismatch'` / assert).

- [ ] **Step 3: Implement.** In `resolve_library`, after the `result` dict is built (after the `manifest_name` line, before the requested-version `warning` block):

```python
        if source in ("cache", "registry"):
            installed = _installed_version(name)
            if installed != lib.version:
                # Honesty flag: the served docs describe a version that is
                # not (or cannot be confirmed to be) the installed one.
                result["version_mismatch"] = True
                result["installed_version"] = installed
                result["resolved_version"] = lib.version
```

Update the `resolve_library` docstring Returns section to mention the flag.

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_mcp_server.py -q` → ALL PASS (including the pre-existing `test_version_mismatch_warning`).

- [ ] **Step 5: Full suite** `.venv/bin/python -m pytest -q` → 570+ passed, 0 failed. Then commit (`ADD: Flag version_mismatch for cache/registry resolutions`).

### Task 3: SDK docs

**Files:**
- Modify: `docs/guides/publishing.md` (idempotent re-run behavior; dist-vs-import naming known limitation), `docs/guides/mcp-server.md` (version_mismatch fields in resolve_library), `docs/architecture/publish/architecture.md` (upsert flow), `docs/architecture/mcp_server/architecture.md:102` (extend the resolve_library row: mismatch vs installed, not just requested).

- [ ] **Step 1:** Invoke the `lcp-writing-documentation` skill; apply its conventions (guides = user-facing kebab-case with examples; architecture = conceptual, no code snippets).
- [ ] **Step 2:** Make the four edits above. In `mcp-server.md`, document the new response fields with a short JSON example showing `"version_mismatch": true, "installed_version": null, "resolved_version": "1.42.1"`.
- [ ] **Step 3:** `pip install -e ".[docs]"` already done in this venv? If `mkdocs` missing: `.venv/bin/pip install -e ".[docs]"`. Run `.venv/bin/mkdocs build --strict` → clean.
- [ ] **Step 4:** Commit (`DOC: Document idempotent publish and version_mismatch honesty`).

---

## Part B — Registry repo

All Part B work in `/Users/andreazanini/Projects/lcp/lcp-registry`. Before starting: `git -C ../lcp-registry checkout main && git -C ../lcp-registry pull`, then `git checkout -b lcp/phase-7-verify-ci`.

### Task 4: `verify_layout.py` — layout / schema / latest.json checks

**Files:**
- Create: `.github/lcp/verify_layout.py`

**Interfaces:**
- Produces: CLI `python .github/lcp/verify_layout.py <manifest-path>...` — exit 0 all pass / exit 1 with `::error::` annotations. Reused by the workflow's fast job.
- Consumes: `sync_latest.compute_latest`, `sync_latest.load_prerelease_policy` (sibling import); `lcp.naming.normalize_package_name`, `lcp.validator.validate_or_raise`, `lcp.models.LCPDocument` (pinned lcp).

- [ ] **Step 1: Write the script:**

```python
#!/usr/bin/env python3
"""Layout, schema and latest.json checks for registry manifests.

Usage: verify_layout.py <manifest-path> [<manifest-path> ...]

For each path (relative to the repo root, e.g.
manifests/python/f/foo/1.0.0.lcp.json.gz) this verifies:

  1. Path shape: manifests/{lang}/{letter}/{slug}/{version}.lcp.json.gz,
     with letter == slug[0] and slug already in canonical PEP 503 form.
  2. The file is valid gzip containing a JSON document that validates
     against the LCP schema (pinned lcp version).
  3. The manifest's library.version equals the filename version and
     library.language equals the {lang} folder.
  4. The package's latest.json exists, has the {"version", "manifest"}
     shape, points at an existing file, and matches the highest stable
     version present on disk (prerelease policy from packages.yaml).

Exit code 0 when every check passes, 1 otherwise (one ::error:: line per
failure, so GitHub Actions annotates the PR).

The folder slug is the normalized PyPI *distribution* name; the manifest's
library.name is the *import* name and MAY differ (python-dateutil vs
dateutil) — no check ties them together.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

from lcp.models import LCPDocument
from lcp.naming import normalize_package_name
from lcp.validator import validate_or_raise

import sync_latest  # sibling module: latest.json policy lives there

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PATH_RE = re.compile(
    r"^manifests/(?P<lang>[a-z0-9-]+)/(?P<letter>[a-z0-9])/"
    r"(?P<slug>[a-z0-9][a-z0-9-]*)/(?P<version>[^/]+)\.lcp\.json\.gz$"
)


def fail(msg: str, failures: list[str]) -> None:
    print(f"::error::{msg}")
    failures.append(msg)


def check_manifest(rel_path: str, failures: list[str]) -> None:
    m = PATH_RE.match(rel_path)
    if not m:
        fail(f"{rel_path}: path does not match "
             "manifests/{lang}/{letter}/{slug}/{version}.lcp.json.gz", failures)
        return
    lang, letter, slug, version = m.group("lang", "letter", "slug", "version")
    if letter != slug[0]:
        fail(f"{rel_path}: letter folder '{letter}' != slug initial '{slug[0]}'",
             failures)
    if normalize_package_name(slug) != slug:
        fail(f"{rel_path}: slug '{slug}' is not canonical "
             f"(expected '{normalize_package_name(slug)}')", failures)

    full = REPO_ROOT / rel_path
    if not full.is_file():
        fail(f"{rel_path}: file not found", failures)
        return
    try:
        raw = gzip.decompress(full.read_bytes())
    except (OSError, gzip.BadGzipFile) as exc:
        fail(f"{rel_path}: not valid gzip: {exc}", failures)
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"{rel_path}: not valid JSON: {exc}", failures)
        return
    try:
        doc = LCPDocument.model_validate(data)
        validate_or_raise(doc)
    except Exception as exc:
        fail(f"{rel_path}: LCP schema validation failed: {exc}", failures)
        return

    lib = doc.manifest.library
    if lib.version != version:
        fail(f"{rel_path}: manifest version '{lib.version}' != "
             f"filename version '{version}'", failures)
    if lib.language != lang:
        fail(f"{rel_path}: manifest language '{lib.language}' != "
             f"folder '{lang}'", failures)


def check_latest(package_dir: Path, failures: list[str]) -> None:
    rel = package_dir.relative_to(REPO_ROOT)
    latest_path = package_dir / "latest.json"
    if not latest_path.is_file():
        fail(f"{rel}/latest.json: missing", failures)
        return
    try:
        pointer = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{rel}/latest.json: unreadable: {exc}", failures)
        return
    version = pointer.get("version")
    manifest = pointer.get("manifest")
    if not version or not manifest or manifest != f"{version}.lcp.json.gz":
        fail(f"{rel}/latest.json: bad shape: {pointer!r}", failures)
        return
    if not (package_dir / manifest).is_file():
        fail(f"{rel}/latest.json: points at missing file '{manifest}'", failures)
        return
    policy = sync_latest.load_prerelease_policy()
    expected = sync_latest.compute_latest(
        sync_latest.list_versions(package_dir),
        include_prereleases=policy.get(package_dir.name, False),
    )
    if expected is not None and version != expected:
        fail(f"{rel}/latest.json: version '{version}' is stale "
             f"(expected '{expected}')", failures)


def main() -> None:
    paths = sys.argv[1:]
    if not paths:
        print("No manifest paths supplied — nothing to verify.")
        return
    failures: list[str] = []
    package_dirs: set[Path] = set()
    for rel_path in paths:
        check_manifest(rel_path, failures)
        parent = (REPO_ROOT / rel_path).parent
        if parent.is_dir():
            package_dirs.add(parent)
    for package_dir in sorted(package_dirs):
        check_latest(package_dir, failures)
    if failures:
        print(f"\n{len(failures)} layout/schema check(s) failed.")
        sys.exit(1)
    print(f"All layout/schema checks passed for {len(paths)} manifest(s).")


if __name__ == "__main__":
    main()
```

Note: `import sync_latest` works because the workflow runs the script with `PYTHONPATH=.github/lcp` (set in Task 6) — same for local runs: `PYTHONPATH=.github/lcp python .github/lcp/verify_layout.py …`.

- [ ] **Step 2: Test locally against real manifests (should pass).** From the SDK venv (has lcp editable-installed = pinned-equivalent):

Run: `cd /Users/andreazanini/Projects/lcp/lcp-registry && PYTHONPATH=.github/lcp /Users/andreazanini/Projects/lcp/lcp/.venv/bin/python .github/lcp/verify_layout.py manifests/python/g/google-adk/2.3.0.lcp.json.gz`
Expected: `All layout/schema checks passed for 1 manifest(s).`, exit 0. (Requires `pyyaml` in the SDK venv for sync_latest — if missing, `.venv/bin/pip show pyyaml` first; it is a dev dep of the SDK, verify.)

- [ ] **Step 3: Test failure paths.** Craft a bad file and confirm exit 1 + `::error::` lines:

```bash
cd /Users/andreazanini/Projects/lcp/lcp-registry
mkdir -p manifests/python/z/zzz-test
cp manifests/python/g/google-adk/2.3.0.lcp.json.gz manifests/python/z/zzz-test/9.9.9.lcp.json.gz
PYTHONPATH=.github/lcp /Users/andreazanini/Projects/lcp/lcp/.venv/bin/python \
  .github/lcp/verify_layout.py manifests/python/z/zzz-test/9.9.9.lcp.json.gz
# Expected: errors for version mismatch (manifest says 2.3.0) + missing latest.json; exit 1
rm -rf manifests/python/z
```

- [ ] **Step 4: Commit** on `lcp/phase-7-verify-ci` (`ADD: Layout/schema/latest verification script`).

### Task 5: `regen_compare.py` — regenerate in isolation and compare

**Files:**
- Create: `.github/lcp/regen_compare.py`
- Create: `.github/lcp/verify-overrides.yaml`

**Interfaces:**
- Produces: CLI `python .github/lcp/regen_compare.py <manifest-path>` — creates a venv in a temp dir, `pip install {slug}=={version}`, rescans `library.name` via `lcp.subprocess_scan.scan_package_subprocess(python=<venv>)`, compares per D3, exit 0/1 with a summary.
- Consumes: pinned `lcp` in the job env; `verify-overrides.yaml`.

- [ ] **Step 1: Write `verify-overrides.yaml`:**

```yaml
# Per-package tolerance overrides for regen_compare.py.
# Changing this file requires PR review — it weakens verification.
#
#   <slug>:
#     symbol_tolerance: 0.05      # fraction of the id-set union (default 0.02)
#     skip_signature_ids:         # ids whose signature is env-dependent
#       - "pkg.mod:func"
{}
```

- [ ] **Step 2: Write `regen_compare.py`:**

```python
#!/usr/bin/env python3
"""Regenerate a submitted manifest in an isolated venv and compare.

Usage: regen_compare.py <manifest-path>   (one manifest per invocation)

Trust model: this is the check that replaces manual review. It installs the
claimed (package, version) from PyPI into a fresh venv — THIS EXECUTES
ARBITRARY CODE and must only run in an ephemeral, secretless environment
(see verify-manifests.yml header) — rescans it with the pinned lcp, and
compares against the submitted manifest:

  * symbol-ID sets: symmetric difference must be <= 2% of the union
    (environment-dependent symbols; override per package in
    verify-overrides.yaml), and
  * signatures: a deterministic sample of up to 50 common symbols must
    match on `signature` and `kind` EXACTLY — no tolerance.

pip install resolves the *distribution* by the folder slug; the rescan
imports the manifest's library.name (the import name).
"""

from __future__ import annotations

import gzip
import json
import math
import re
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

import yaml
from lcp.models import LCPDocument
from lcp.subprocess_scan import scan_package_subprocess

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OVERRIDES_FILE = Path(__file__).resolve().parent / "verify-overrides.yaml"
PATH_RE = re.compile(
    r"^manifests/(?P<lang>[a-z0-9-]+)/(?P<letter>[a-z0-9])/"
    r"(?P<slug>[a-z0-9][a-z0-9-]*)/(?P<version>[^/]+)\.lcp\.json\.gz$"
)
DEFAULT_TOLERANCE = 0.02
SAMPLE_SIZE = 50
SCAN_TIMEOUT = 600.0


def load_overrides(slug: str) -> tuple[float, set[str]]:
    data = yaml.safe_load(OVERRIDES_FILE.read_text(encoding="utf-8")) or {}
    entry = data.get(slug) or {}
    return (
        float(entry.get("symbol_tolerance", DEFAULT_TOLERANCE)),
        set(entry.get("skip_signature_ids", [])),
    )


def main() -> None:
    rel_path = sys.argv[1]
    m = PATH_RE.match(rel_path)
    if not m:
        print(f"::error::{rel_path}: unexpected manifest path")
        sys.exit(1)
    slug, version = m.group("slug", "version")

    submitted = LCPDocument.model_validate(
        json.loads(gzip.decompress((REPO_ROOT / rel_path).read_bytes()))
    )
    import_name = submitted.manifest.library.name
    tolerance, skip_signatures = load_overrides(slug)

    with tempfile.TemporaryDirectory() as tmp:
        env_dir = Path(tmp) / "venv"
        print(f"Creating venv and installing {slug}=={version} …")
        venv.create(env_dir, with_pip=True)
        py = env_dir / "bin" / "python"
        install = subprocess.run(
            [str(py), "-m", "pip", "install", "--quiet",
             f"{slug}=={version}"],
            capture_output=True, text=True,
        )
        if install.returncode != 0:
            print(f"::error::pip install {slug}=={version} failed:\n"
                  f"{install.stderr[-2000:]}")
            sys.exit(1)
        print(f"Rescanning import '{import_name}' with pinned lcp …")
        regen = scan_package_subprocess(
            import_name, python=str(py), timeout=SCAN_TIMEOUT
        )

    sub_ids = {s.id for s in submitted.symbols}
    new_ids = {s.id for s in regen.symbols}
    union = sub_ids | new_ids
    diff = sub_ids ^ new_ids
    allowed = math.ceil(tolerance * len(union))
    print(f"symbols: submitted={len(sub_ids)} regenerated={len(new_ids)} "
          f"symmetric-diff={len(diff)} allowed={allowed}")
    failures: list[str] = []
    if len(diff) > allowed:
        only_sub = sorted(sub_ids - new_ids)[:20]
        only_new = sorted(new_ids - sub_ids)[:20]
        failures.append(
            f"symbol-ID sets differ by {len(diff)} (> {allowed} allowed): "
            f"only-in-submission={only_sub} only-in-regen={only_new}"
        )

    sub_by_id = {s.id: s for s in submitted.symbols}
    new_by_id = {s.id: s for s in regen.symbols}
    common = sorted(sub_ids & new_ids)
    step = max(1, len(common) // SAMPLE_SIZE)
    sampled = common[::step][:SAMPLE_SIZE]
    for sid in sampled:
        if sid in skip_signatures:
            continue
        a, b = sub_by_id[sid], new_by_id[sid]
        if (a.signature or "") != (b.signature or "") or a.kind != b.kind:
            failures.append(
                f"signature mismatch for '{sid}': submitted "
                f"{a.kind}/{a.signature!r} vs regenerated {b.kind}/{b.signature!r}"
            )
    print(f"spot-checked {len(sampled)} common symbols "
          f"({len(skip_signatures)} skipped by override)")

    if failures:
        for f in failures:
            print(f"::error::{rel_path}: {f}")
        sys.exit(1)
    print(f"{rel_path}: regeneration comparison PASSED")


if __name__ == "__main__":
    main()
```

Field access note: verify the actual attribute names on `lcp.models.Symbol` (`id`, `kind`, `signature`) against `src/lcp/models.py` before running; `kind` is an enum — compare `a.kind == b.kind` directly.

- [ ] **Step 3: Test locally — positive case** (google-adk 2.3.0 is small enough):

Run: `cd /Users/andreazanini/Projects/lcp/lcp-registry && PYTHONPATH=.github/lcp /Users/andreazanini/Projects/lcp/lcp/.venv/bin/python .github/lcp/regen_compare.py manifests/python/g/google-adk/2.3.0.lcp.json.gz`
Expected: `regeneration comparison PASSED`, exit 0. **Caveat:** the on-disk google-adk manifest is pre-freeze (no Phase-4 fields) but the comparison only reads symbol ids/kind/signature, which are stable — if it fails on set-diff instead, inspect: it may reveal real env drift; record findings, do not weaken the gate to force a pass.

- [ ] **Step 4: Test locally — negative case** (the exit-criterion attack, rehearsed):

```bash
cd /Users/andreazanini/Projects/lcp/lcp-registry
python3 - <<'EOF'
import gzip, json
p = "manifests/python/g/google-adk/2.3.0.lcp.json.gz"
d = json.loads(gzip.decompress(open(p, "rb").read()))
# tamper: rewrite the first function symbol's signature
for s in d["symbols"]:
    if s.get("signature"):
        s["signature"] = "(totally_fake_arg: int) -> None"
        print("tampered:", s["id"]); break
open("/tmp/tampered.lcp.json.gz", "wb").write(gzip.compress(json.dumps(d).encode()))
EOF
mkdir -p manifests/python/g/google-adk-tamper-test
cp /tmp/tampered.lcp.json.gz manifests/python/g/google-adk-tamper-test/2.3.0.lcp.json.gz
# run compare against the tampered file via a copy at the REAL path:
cp manifests/python/g/google-adk/2.3.0.lcp.json.gz /tmp/orig-backup.gz
cp /tmp/tampered.lcp.json.gz manifests/python/g/google-adk/2.3.0.lcp.json.gz
PYTHONPATH=.github/lcp /Users/andreazanini/Projects/lcp/lcp/.venv/bin/python \
  .github/lcp/regen_compare.py manifests/python/g/google-adk/2.3.0.lcp.json.gz
echo "exit: $?"   # Expected: signature mismatch error, exit 1
cp /tmp/orig-backup.gz manifests/python/g/google-adk/2.3.0.lcp.json.gz
rm -rf manifests/python/g/google-adk-tamper-test
git status --short   # must be clean
```

**Sampling caveat:** the tampered symbol must be in the deterministic sample; tamper the FIRST symbol with a signature (sorted order puts it early). If it happens to be skipped by the every-k-th stride, tamper a symbol whose id you confirm is in `sampled` (print `sampled` in a debug run). The negative test must genuinely fail the check.

- [ ] **Step 5: Commit** (`ADD: Regenerate-and-compare verification script`).

### Task 6: `verify-manifests.yml` workflow + lcp pin

**Files:**
- Create: `.github/workflows/verify-manifests.yml`
- Modify: `.github/lcp/requirements.txt`

- [ ] **Step 1:** Get the pin SHA: `git -C /Users/andreazanini/Projects/lcp/lcp rev-parse roadmap/agentic-improvements` (= 98efe82…, full 40 chars; it is pushed — verify with `git -C /Users/andreazanini/Projects/lcp/lcp branch -r --contains 98efe82`).

- [ ] **Step 2:** Update `.github/lcp/requirements.txt` (used by weekly updater AND the new workflow — keeps every regeneration on the same lcp):

```
# lcp is pinned to an exact SDK commit: every manifest in this registry is
# generated and verified with the SAME code. Bump ONLY together with a
# planned registry-wide regeneration (see README "Verification & trust").
lcp @ git+https://github.com/zazza123/lcp@<FULL-40-CHAR-SHA>
packaging>=24.0
pyyaml>=6.0
requests>=2.32.0
```

- [ ] **Step 3:** Write `.github/workflows/verify-manifests.yml`:

```yaml
name: Verify Manifests

# Automated trust: a green check on this workflow replaces manual review of
# manifest submissions.
#
# SECURITY MODEL — the `regenerate` job pip-installs the (package, version)
# claimed by the PR from PyPI, which EXECUTES ARBITRARY CODE. Containment:
#   * trigger is `pull_request` (never pull_request_target): fork PRs run
#     with a read-only GITHUB_TOKEN and NO access to repository secrets;
#   * workflow-level `permissions: contents: read`;
#   * GitHub-hosted runners are ephemeral VMs, destroyed after each job;
#   * network egress used: pypi.org + files.pythonhosted.org (package
#     download), github.com (checkout + pinned lcp install).
# Do not add secrets to this workflow. Do not change the trigger.

on:
  pull_request:
    paths:
      - 'manifests/**'

permissions:
  contents: read

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      manifests: ${{ steps.diff.outputs.manifests }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: List added/changed manifest files
        id: diff
        run: |
          FILES=$(git diff --name-only --diff-filter=AM \
            "origin/${{ github.base_ref }}...HEAD" -- 'manifests/**/*.lcp.json.gz')
          echo "$FILES"
          echo "manifests=$(echo "$FILES" | jq -R -s -c 'split("\n") | map(select(length > 0))')" >> "$GITHUB_OUTPUT"

  layout:
    needs: detect
    if: needs.detect.outputs.manifests != '[]'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install pinned lcp + deps
        run: pip install -r .github/lcp/requirements.txt
      - name: Layout / schema / latest.json checks
        env:
          MANIFESTS: ${{ needs.detect.outputs.manifests }}
        run: |
          echo "$MANIFESTS" | jq -r '.[]' | xargs \
            env PYTHONPATH=.github/lcp python .github/lcp/verify_layout.py

  regenerate:
    needs: detect
    if: needs.detect.outputs.manifests != '[]'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        manifest: ${{ fromJSON(needs.detect.outputs.manifests) }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install pinned lcp + deps
        run: pip install -r .github/lcp/requirements.txt
      - name: Regenerate and compare (runs untrusted package code)
        run: |
          PYTHONPATH=.github/lcp python .github/lcp/regen_compare.py \
            "${{ matrix.manifest }}"
```

Injection note: `matrix.manifest` values come from `git diff --name-only` (repo paths); they are quoted and the detect regex-free path is still fed through `verify_layout.py`'s strict `PATH_RE` in the layout job. Paths with shell metacharacters cannot match `PATH_RE` and layout fails first; still keep the argument quoted as shown.

- [ ] **Step 4:** Validate workflow syntax locally: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/verify-manifests.yml'))"` → no error. (Real validation happens when the PR runs it — the negative-test PR in Task 11 exercises both jobs.)

- [ ] **Step 5: Commit** (`ADD: Verify-manifests CI workflow with pinned lcp`).

### Task 7: `populate.py` + `population.yaml`

**Files:**
- Create: `.github/lcp/population.yaml`
- Create: `.github/lcp/populate.py`

**Interfaces:**
- Produces: `python .github/lcp/populate.py --only <name,...>` / `--all` / `--regen` writes `manifests/python/{letter}/{slug}/{version}.lcp.json.gz` + `latest.json` into the working tree and prints a per-package report. It never touches git — branching/commits are explicit plan steps (Task 10).
- Consumes: `lcp.subprocess_scan.scan_package_subprocess`, `lcp.naming.normalize_package_name`, `lcp.validator.validate_or_raise`, `sync_latest.compute_latest`; run with the SDK repo's venv (`/Users/andreazanini/Projects/lcp/lcp/.venv/bin/python`), which has the pinned-equivalent lcp editable-installed and `requests`/`pyyaml`.

- [ ] **Step 1: Build the frozen target list.** Fetch the top-PyPI dump and generate `population.yaml` (run from the registry repo root):

```bash
/Users/andreazanini/Projects/lcp/lcp/.venv/bin/python - <<'EOF'
import json, urllib.request, yaml
URL = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages.min.json"
rows = json.loads(urllib.request.urlopen(URL, timeout=30).read())["rows"]
EXCLUDE = {
    # packaging / build infra — no importable API worth serving
    "pip", "setuptools", "wheel", "packaging", "virtualenv", "distlib",
    "pkginfo", "twine", "build", "installer", "poetry", "poetry-core",
    "pipenv", "hatchling", "flit-core", "setuptools-scm", "pip-tools",
    # CLI-only tools
    "awscli",
}
def keep(name):
    return (name not in EXCLUDE and not name.startswith("types-")
            and not name.endswith("-stubs"))
top = [r["project"] for r in rows if keep(r["project"])][:100]
if "polars" not in top:          # exit-criterion package, force-include
    top[-1] = "polars"
# import-name overrides for dist != import packages in the selection
KNOWN_IMPORTS = {
    "python-dateutil": "dateutil", "pyyaml": "yaml", "pillow": "PIL",
    "beautifulsoup4": "bs4", "protobuf": "google.protobuf",
    "scikit-learn": "sklearn", "opencv-python": "cv2",
    "python-dotenv": "dotenv", "pyjwt": "jwt", "attrs": "attr",
    "typing-extensions": "typing_extensions",
}
entries = [{"name": n, **({"import": KNOWN_IMPORTS[n]} if n in KNOWN_IMPORTS else {})}
           for n in top]
with open(".github/lcp/population.yaml", "w") as fh:
    fh.write("# Frozen top-100 population targets (source: hugovk "
             "top-pypi-packages,\n# fetched 2026-07-08; exclusions: packaging "
             "infra, stubs, CLI-only).\n# 'import' overrides the import name "
             "when it differs from the dist name.\npython:\n")
    yaml.safe_dump(entries, fh, default_flow_style=False)
EOF
```

Then **review the generated list by hand**: open the file, sanity-check ~100 entries, remove anything obviously non-library that slipped through, confirm `polars` present. The frozen file is the reviewable artifact — the fetch script is not committed.

- [ ] **Step 2: Write `populate.py`:**

```python
#!/usr/bin/env python3
"""Batch pre-population of the LCP registry (run LOCALLY by a maintainer).

Reads population.yaml, and for each target package:
  1. resolves the newest stable version from PyPI (or explicit versions
     in --regen mode),
  2. creates a throwaway venv and pip-installs dist==version,
  3. scans the import name with the checked-out lcp
     (lcp.subprocess_scan machinery — the venv does not need lcp),
  4. validates the document and writes
     manifests/python/{letter}/{slug}/{version}.lcp.json.gz (+ latest.json,
     recomputed via sync_latest.compute_latest; never downgraded).

Idempotent/resumable: existing manifest files are skipped unless
--regen. Failures are reported per package and never abort the run —
the final report lists exactly what landed and what didn't (no silent
gaps). Git is untouched: review `git status` afterwards, then commit.

Usage (from the registry repo root, with the SDK venv's python):
  populate.py --all            # every population.yaml target, newest stable
  populate.py --only a,b,c     # subset
  populate.py --regen a,b      # regenerate ALL versions already on disk
  populate.py --workers 4      # parallel venv builds (default 2)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import venv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml
from packaging.version import InvalidVersion, Version

from lcp.naming import normalize_package_name
from lcp.subprocess_scan import scan_package_subprocess
from lcp.validator import validate_or_raise

import sync_latest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
POPULATION_YAML = Path(__file__).resolve().parent / "population.yaml"
MANIFESTS_ROOT = REPO_ROOT / "manifests" / "python"
SCAN_TIMEOUT = 600.0


def newest_stable(dist: str) -> str:
    with urllib.request.urlopen(
        f"https://pypi.org/pypi/{dist}/json", timeout=30
    ) as resp:
        releases = json.load(resp).get("releases", {})
    versions = []
    for v_str, files in releases.items():
        if not files or all(f.get("yanked") for f in files):
            continue
        try:
            v = Version(v_str)
        except InvalidVersion:
            continue
        if not v.is_prerelease:
            versions.append((v, v_str))
    if not versions:
        raise RuntimeError(f"{dist}: no stable release on PyPI")
    return max(versions)[1]


def detect_import_name(py: Path, dist: str) -> str:
    """Map dist -> top-level import name inside the venv."""
    code = (
        "import json, sys\n"
        "from importlib.metadata import packages_distributions\n"
        "from lcp.naming import normalize_package_name as norm\n"
        f"target = norm({dist!r})\n"
        "hits = sorted(imp for imp, dists in packages_distributions().items()\n"
        "              if target in (norm(d) for d in dists)\n"
        "              and not imp.startswith('_'))\n"
        "print(json.dumps(hits))\n"
    )
    lcp_parent = str(Path(sys.modules["lcp"].__file__).resolve().parent.parent)
    out = subprocess.run(
        [str(py), "-c", code], capture_output=True, text=True, timeout=60,
        env={"PYTHONPATH": lcp_parent, "PATH": "/usr/bin:/bin"},
    )
    hits = json.loads(out.stdout or "[]")
    if not hits:
        raise RuntimeError(f"{dist}: could not detect import name")
    slug = normalize_package_name(dist)
    for h in hits:
        if normalize_package_name(h) == slug:
            return h
    return hits[0]


def build_one(dist: str, version: str, import_override: str | None) -> str:
    slug = normalize_package_name(dist)
    pkg_dir = MANIFESTS_ROOT / slug[0] / slug
    out_path = pkg_dir / f"{version}.lcp.json.gz"
    with tempfile.TemporaryDirectory(prefix=f"lcp-pop-{slug}-") as tmp:
        env_dir = Path(tmp) / "venv"
        venv.create(env_dir, with_pip=True)
        py = env_dir / "bin" / "python"
        install = subprocess.run(
            [str(py), "-m", "pip", "install", "--quiet", f"{dist}=={version}"],
            capture_output=True, text=True, timeout=1200,
        )
        if install.returncode != 0:
            raise RuntimeError(
                f"pip install failed: {install.stderr.strip()[-500:]}"
            )
        import_name = import_override or detect_import_name(py, dist)
        doc = scan_package_subprocess(
            import_name, python=str(py), timeout=SCAN_TIMEOUT
        )
    validate_or_raise(doc)
    pkg_dir.mkdir(parents=True, exist_ok=True)
    import gzip
    out_path.write_bytes(gzip.compress(doc.to_json(indent=2).encode("utf-8")))
    # latest.json: recompute from disk, stable-only policy (never downgrades)
    latest = sync_latest.compute_latest(
        sync_latest.list_versions(pkg_dir), include_prereleases=False
    )
    if latest:
        (pkg_dir / "latest.json").write_text(
            json.dumps(
                {"version": latest, "manifest": f"{latest}.lcp.json.gz"},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
    return f"{slug}=={version}: {len(doc.symbols)} symbols -> {out_path.relative_to(REPO_ROOT)}"


def main() -> None:
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--only", type=str)
    group.add_argument("--regen", type=str)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    config = yaml.safe_load(POPULATION_YAML.read_text(encoding="utf-8"))
    targets = {e["name"]: e.get("import") for e in config["python"]}

    jobs: list[tuple[str, str, str | None]] = []  # (dist, version, import)
    if args.regen:
        for dist in args.regen.split(","):
            slug = normalize_package_name(dist.strip())
            pkg_dir = MANIFESTS_ROOT / slug[0] / slug
            for gz in sorted(pkg_dir.glob("*.lcp.json.gz")):
                version = gz.name[: -len(".lcp.json.gz")]
                jobs.append((dist.strip(), version, targets.get(dist.strip())))
    else:
        names = (
            list(targets) if args.all
            else [n.strip() for n in args.only.split(",")]
        )
        for dist in names:
            slug = normalize_package_name(dist)
            try:
                version = newest_stable(dist)
            except Exception as exc:
                print(f"FAIL {dist}: {exc}")
                continue
            out = MANIFESTS_ROOT / slug[0] / slug / f"{version}.lcp.json.gz"
            if out.exists():
                print(f"SKIP {dist}=={version} (already on disk)")
                continue
            jobs.append((dist, version, targets.get(dist)))

    ok, failed = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {
            pool.submit(build_one, d, v, imp): (d, v) for d, v, imp in jobs
        }
        for fut in as_completed(futs):
            dist, version = futs[fut]
            try:
                msg = fut.result()
                ok.append(msg)
                print(f"OK   {msg}")
            except Exception as exc:
                failed.append(f"{dist}=={version}: {exc}")
                print(f"FAIL {dist}=={version}: {exc}")

    print(f"\n=== populate report: {len(ok)} ok, {len(failed)} failed, "
          f"{len(jobs)} attempted ===")
    for line in failed:
        print(f"  FAILED  {line}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke-test on ONE small package** (from the registry root):

Run: `PYTHONPATH=.github/lcp /Users/andreazanini/Projects/lcp/lcp/.venv/bin/python .github/lcp/populate.py --only six`
Expected: `OK six==1.17.0: … symbols -> manifests/python/s/six/1.17.0.lcp.json.gz`, `git status` shows the new gz + latest.json. Then `git checkout -- manifests && git clean -fd manifests` (the smoke output is regenerated for real in Task 10 — keep PR #1 code-only).

- [ ] **Step 4: Commit** scripts + population.yaml (`ADD: Batch population script and frozen top-100 target list`).

### Task 8: Registry docs (README, SECURITY)

**Files:**
- Modify: `README.md` — new section **"Verification & trust"**: green `Verify Manifests` check replaces manual review; hard gates list; the 2%/50-sample tolerance policy verbatim from D3; overrides file requires review; lcp pin + bump policy; known limitations (no signing/attestation of manifests, raw.githubusercontent hosting only).
- Modify: `.github/SECURITY.md` — paragraph on the regenerate job's arbitrary-code-execution containment (D6 list: pull_request trigger, read-only token, no secrets, ephemeral runners, documented egress).

- [ ] **Step 1:** Write both sections (registry repo has no docs skill — plain clear markdown consistent with the existing README voice).
- [ ] **Step 2:** Commit (`DOC: Document verification trust model and CI security posture`).

### Task 9: Registry infra PR — open, watch, merge

- [ ] **Step 1:** Push branch: `git push -u origin lcp/phase-7-verify-ci`.
- [ ] **Step 2:** Open PR to `main`: title `ADD: Manifest verification CI and batch population tooling`; body summarizing D1–D7 decisions, the security model, and noting manifests are untouched. Footer per session rules (no session links).
- [ ] **Step 3:** `gh pr checks <n> --watch` — note: `verify-manifests.yml` will NOT trigger (no `manifests/**` change) and `validate-manifests.yml` also won't; expect only CodeQL/default checks if configured. Fix any findings in session.
- [ ] **Step 4:** Check review comments (`gh pr view <n> --comments`), including bots. Resolve, then merge (`gh pr merge <n> --merge`), `git checkout main && git pull`.

### Task 10: Population run + batch PRs

- [ ] **Step 1: Regen batch first** (the 6 pre-freeze libraries, 10 files, same versions):

```bash
cd /Users/andreazanini/Projects/lcp/lcp-registry
git checkout -b lcp/populate/regen-prefreeze main
PYTHONPATH=.github/lcp /Users/andreazanini/Projects/lcp/lcp/.venv/bin/python \
  .github/lcp/populate.py --regen \
  azure-ai-contentunderstanding,firebase-admin,google-adk,google-cloud-aiplatform,google-cloud-firestore,google-genai \
  --workers 4
git add manifests && git commit  # "UPD: Regenerate 10 pre-freeze manifests with Phase 4 structured fields"
git push -u origin lcp/populate/regen-prefreeze
gh pr create --title "UPD: Regenerate pre-freeze manifests (structured fields)" ...
gh pr checks --watch   # verify-manifests regenerates all 10 in matrix
```

Expected: `latest.json` files unchanged (`git diff --stat` shows only `.gz` files). If a package's old version no longer pip-installs cleanly, report it in the PR body and drop that file from the batch (documented, not silent).

- [ ] **Step 2: Top-100 batches.** Run the full population locally, then split into 5 PRs of ~20 packages by alphabetical order (batch = the set of package dirs touched):

```bash
git checkout main && git pull && git checkout -b lcp/populate/batch-01
PYTHONPATH=.github/lcp /Users/andreazanini/Projects/lcp/lcp/.venv/bin/python \
  .github/lcp/populate.py --all --workers 4 | tee /tmp/populate-report.txt
```

(One run writes everything; `--all` skips files that already exist, so re-runs after failures are cheap.) Then per batch: `git add manifests/python/<letters for this batch>`, commit `ADD: Pre-population batch N (<count> packages)` with the package list in the body, push, PR, **`gh pr checks --watch`** (the matrix regenerates each manifest), fix or drop failures, merge, next batch from updated `main`. Timebox: if a package repeatedly fails CI for env-divergence, either add a reviewed `verify-overrides.yaml` entry (if the diff is legitimately environmental and < ~5%) or drop the package and record it in the final report — never weaken the default tolerance.

- [ ] **Step 3: Final population report.** Record in the last batch PR body (and in the roadmap Status line): N of 100 published, list of dropped packages with reasons.

### Task 11: Exit criterion — wrong manifest rejected by CI

- [ ] **Step 1:** Branch `lcp/exit-test-tampered`: take a small merged manifest (e.g. `six`), tamper one sampled function's `signature` (script from Task 5 Step 4), overwrite the file, commit (`TST: Tampered manifest — must be rejected by CI`), push, open PR titled `TST: Exit-criterion check — tampered manifest (DO NOT MERGE)`.
- [ ] **Step 2:** `gh pr checks --watch` → the `regenerate` job MUST fail with a `signature mismatch` annotation. Screenshot/quote the failure line.
- [ ] **Step 3:** Close the PR without merging (`gh pr close`), delete the branch. Record the PR number as exit-criterion evidence in the roadmap Status.

### Task 12: Exit criterion — fresh-machine `resolve_library("polars")` < 2s

- [ ] **Step 1:** Build a throwaway venv WITHOUT polars (the SDK venv has polars installed — it would win via live scan):

```bash
python3.12 -m venv /private/tmp/claude-501/*/scratchpad/freshenv 2>/dev/null || \
python3.12 -m venv "$SCRATCH/freshenv"   # use the session scratchpad path
"$SCRATCH/freshenv/bin/pip" install -q -e /Users/andreazanini/Projects/lcp/lcp
```

- [ ] **Step 2:** Time the resolution (cache empty, polars not installed → failed scan → registry latest.json → manifest):

```bash
"$SCRATCH/freshenv/bin/python" - <<'EOF'
import time, tempfile
from pathlib import Path
from lcp.mcp_server import resolve_library_document
t0 = time.perf_counter()
doc, source = resolve_library_document(
    "polars",
    cache_dir=Path(tempfile.mkdtemp()),
    registry_url="https://raw.githubusercontent.com/zazza123/lcp-registry/refs/heads/main",
)
dt = time.perf_counter() - t0
print(f"source={source} version={doc.manifest.library.version} "
      f"symbols={len(doc.symbols)} elapsed={dt:.2f}s")
assert source == "registry" and dt < 2.0
EOF
```

Expected: `source=registry … elapsed=<2s`, assert passes. If >2s, measure the split (failed-scan time vs fetch time) before touching anything — raw.githubusercontent latency varies; rerun 3×, record median. Record the number in the roadmap Status.

### Task 13: Close out — SDK suite, roadmap, SDK PR

- [ ] **Step 1:** SDK repo: `.venv/bin/python -m pytest -q` → all green (570+); `bash tests/plugin/run_all.sh` → green; `.venv/bin/ruff check src/lcp && .venv/bin/ruff check tests` → clean; `.venv/bin/mkdocs build --strict` → clean.
- [ ] **Step 2:** Update roadmap Phase 7 **Status** line (done + date, registry PR numbers, population count, exit-criteria evidence: tampered-PR number rejected, polars timing). No eval-log row. `git add -f docs/superpowers/plans/...` both roadmap and this plan; commit (`UPD: Phase 7 status in the roadmap`).
- [ ] **Step 3:** Push `roadmap/phase-7-registry`; open PR to `roadmap/agentic-improvements`: title `MRG: Phase 7 — registry CI verification + pre-population (SDK side)`. Body: what changed in the SDK (idempotent publish, version_mismatch honesty, docs) + pointers to the registry PRs. No session links.
- [ ] **Step 4:** `gh pr checks --watch`; resolve CI failures and review/bot comments (CodeQL etc.) in session. Done when green and comments addressed.

---

## Self-Review Notes

- Spec coverage: CI verify (Tasks 4–6, 9), security caveat (D6 + Task 6 header + Task 8), pre-population top-100 (D4, Tasks 7, 10), 6 pre-freeze regen (Task 10 Step 1), idempotent publish (Task 1), latest.json maintenance (D2, verify_layout + populate), version-mismatch honesty (Task 2), `normalize_package_name` reuse (all scripts import it, none reimplement), scope-outs documented (Task 8), exit criteria (Tasks 11, 12 + negative rehearsal in Task 5).
- Known deliberate deviation: population does not use `publish.py` (D1, motivated).
- Type consistency: `scan_package_subprocess(package, python, timeout) -> LCPDocument` matches `src/lcp/subprocess_scan.py:111`; `compute_latest(versions, *, include_prereleases)` and `list_versions(dir)` match `sync_latest.py`; `normalize_package_name` matches `naming.py`.
