# Publishing

`lcp publish` submits an LCP manifest to the central registry (or your own registry repo) by opening a Pull Request with the manifest and structured metadata.

## How publishing works

Publishing uses a fork-and-PR flow against the central registry at `zazza123/lcp-registry` (the value of `_DEFAULT_REGISTRY_REPO` in `src/lcp/publish.py`). When you run `lcp publish`, the command authenticates with GitHub, forks the registry repo into your account if a fork does not already exist, creates a branch named `lcp/add/<slug>/<version>`, gzip-compresses the manifest, and pushes it to the correct sharded path on that branch. The `<slug>` is the hyphenated package name (a dotted name like `google.adk` becomes `google-adk`). It then opens a pull request against the upstream `main` branch titled `NEW: Manifest <package> <version> (<language>)`, labelled `new_manifest`, `lcp-publish`, and the language, with a structured body listing package metadata and a checklist.

A GitHub personal access token is required. The token must have the `repo` scope (for private registries) or `public_repo` scope (for the public registry). You can supply it via the `--token` flag or by setting the `LCP_GITHUB_TOKEN` (or `GITHUB_TOKEN`) environment variable. The tool does not store credentials; it passes the token directly to the GitHub API for each request.

## Quick start

```bash
export LCP_GITHUB_TOKEN=ghp_...
lcp publish <package-name>
```

On success, `lcp publish` prints the URL of the newly opened pull request. If authentication fails, the command exits with a clear error message indicating the required token scope. Publishing is not fully idempotent at the GitHub level — if a branch for the same `(package, version)` tuple already exists on your fork, the command will fail with a GitHub API error rather than silently overwriting it.

## CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `PACKAGE` | (required) | Importable name of the installed Python package to publish. |
| `--token` | `LCP_GITHUB_TOKEN` env | GitHub personal access token with `repo` or `public_repo` scope. Also reads `GITHUB_TOKEN`. |
| `--registry-repo` | `zazza123/lcp-registry` | Target registry repository in `owner/name` format. |
| `--file` | (none) | Path to an existing `.lcp.json` file; skips scanning. |
| `--include-private` | off | Include private symbols (names starting with `_`) in the manifest. |
| `--no-recursive` | off | Skip submodule scanning; only scan the top-level package. |
| `--dry-run` | off | Generate the manifest and show what would be submitted without creating a PR. |

**Example:**

```bash
lcp publish requests --include-private --dry-run
```

## Publishing to a private registry

Pass `--registry-repo owner/repo` to target a different registry. This is useful for organizations that maintain an internal registry alongside or instead of the public one.

```bash
lcp publish mylib --registry-repo my-org/my-lcp-registry --token ghp_...
```

For private registries, the token must have full `repo` scope so the command can fork, push to, and open PRs against a private repository. For the public registry, `public_repo` scope is sufficient.

## Registry layout

Manifests are stored in a sharded directory structure that keeps directory sizes manageable and reduces merge conflicts when many packages are submitted in parallel. Each manifest is gzip-compressed (typically a ~70% size reduction).

```text
lcp-registry/
├── manifests/
│   └── python/
│       ├── f/
│       │   └── flask/
│       │       └── 3.0.0.lcp.json.gz
│       ├── n/
│       │   └── numpy/
│       │       ├── 1.26.0.lcp.json.gz
│       │       └── 2.0.0.lcp.json.gz
│       └── r/
│           └── requests/
│               └── 2.31.0.lcp.json.gz
└── README.md
```

The path template is:

```
manifests/{language}/{first_letter}/{slug}/{version}.lcp.json.gz
```

The `{slug}` is the package name normalized to its canonical form: runs of `.`, `-`, and `_` collapse to a single `-` and the name is lowercased. So `requests` version `2.31.0` lands at `manifests/python/r/requests/2.31.0.lcp.json.gz`, while a dotted name like `google.adk` lands at `manifests/python/g/google-adk/2.2.0.lcp.json.gz`. The first-letter shard prevents any single directory from accumulating thousands of entries. Each package folder also carries a `latest.json` pointer (`{"version": ..., "manifest": ...}`) that the MCP server reads to resolve the newest manifest when no version is requested.

## Programmatic usage

```python
from lcp import scan
from lcp.publish import publish_manifest

doc = scan("requests")
result = publish_manifest(
    doc,
    token="ghp_...",
    registry_repo="zazza123/lcp-registry",  # optional, this is the default
)
print(result.pr_url)   # https://github.com/zazza123/lcp-registry/pull/<n>
print(result.manifest_path)  # manifests/python/r/requests/2.31.0.lcp.json.gz
```

`publish_manifest(document, token, registry_repo=...)` accepts a validated `LCPDocument`, a GitHub token string, and an optional `registry_repo` argument (default: `"zazza123/lcp-registry"`). It returns a `PublishResult` dataclass with fields `pr_url`, `pr_number`, `manifest_path`, `package_name`, `package_version`, and `language`. On failure it raises `PublishError` (for GitHub API, network, or permission errors) or `ValueError` (for a malformed `registry_repo` string).

## See also

- [CLI reference](../cli.md#lcp-publish) — full flag list.
