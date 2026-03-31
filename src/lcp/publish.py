"""Publish LCP manifests to the registry via GitHub Pull Request."""

from __future__ import annotations

import base64
import gzip
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .models import LCPDocument

_DEFAULT_REGISTRY_REPO = "zazza123/lcp-registry"
_GITHUB_API_BASE = "https://api.github.com"
_FORK_POLL_INTERVAL = 2
_FORK_POLL_MAX_ATTEMPTS = 30
_REQUEST_TIMEOUT = 30

_PR_LABELS = ["new_manifest"]


class PublishError(Exception):
    """Error during publish operation."""


@dataclass
class PublishResult:
    """Result of a publish operation."""

    pr_url: str
    pr_number: int
    manifest_path: str
    package_name: str
    package_version: str
    language: str


def _github_request(
    method: str,
    url: str,
    token: str,
    data: dict | None = None,
    timeout: int = _REQUEST_TIMEOUT,
) -> dict:
    """Make an authenticated GitHub API request.

    Args:
        method: HTTP method (GET, POST, PUT).
        url: Full GitHub API URL.
        token: GitHub personal access token.
        data: Optional JSON body.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response as a dictionary.

    Raises:
        PublishError: On authentication, permission, or API errors.
    """
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if body:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            resp_body = response.read()
            if not resp_body:
                return {}
            return json.loads(resp_body)
    except urllib.error.HTTPError as exc:
        resp_text = ""
        try:
            resp_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        if exc.code == 401:
            raise PublishError(
                "Invalid or expired GitHub token. "
                "Ensure your token has 'repo' or 'public_repo' scope."
            ) from exc
        if exc.code == 403:
            raise PublishError(
                "GitHub token lacks required permissions. "
                "Ensure your token has 'repo' or 'public_repo' scope."
            ) from exc

        message = ""
        try:
            error_data = json.loads(resp_text)
            message = error_data.get("message", "")
        except (json.JSONDecodeError, ValueError):
            message = resp_text[:200] if resp_text else ""

        raise PublishError(
            f"GitHub API error (HTTP {exc.code}): {message}"
        ) from exc
    except urllib.error.URLError as exc:
        raise PublishError(
            f"Network error communicating with GitHub: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise PublishError(
            "Request to GitHub API timed out"
        ) from exc


def _get_authenticated_user(token: str) -> str:
    """Get the authenticated user's GitHub username.

    Args:
        token: GitHub personal access token.

    Returns:
        GitHub username.

    Raises:
        PublishError: If authentication fails.
    """
    user_data = _github_request("GET", f"{_GITHUB_API_BASE}/user", token)
    username = user_data.get("login")
    if not username:
        raise PublishError("Could not determine GitHub username from token")
    return username


def _ensure_fork(
    username: str,
    registry_repo: str,
    token: str,
) -> str:
    """Ensure a fork of the registry repo exists for the user.

    Creates a fork if one does not already exist, and waits for it
    to become available.

    Args:
        username: GitHub username.
        registry_repo: Registry repo in ``owner/name`` format.
        token: GitHub personal access token.

    Returns:
        Full name of the fork (``username/repo-name``).

    Raises:
        PublishError: If fork creation fails or times out.
    """
    owner, repo = registry_repo.split("/", 1)

    # Check if fork already exists
    fork_full_name = f"{username}/{repo}"
    try:
        _github_request(
            "GET", f"{_GITHUB_API_BASE}/repos/{fork_full_name}", token
        )
        return fork_full_name
    except PublishError:
        pass  # Fork doesn't exist, create it

    # Create fork
    _github_request(
        "POST",
        f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/forks",
        token,
    )

    # Poll until fork is ready
    for _ in range(_FORK_POLL_MAX_ATTEMPTS):
        time.sleep(_FORK_POLL_INTERVAL)
        try:
            _github_request(
                "GET", f"{_GITHUB_API_BASE}/repos/{fork_full_name}", token
            )
            return fork_full_name
        except PublishError:
            continue

    raise PublishError(
        f"Timed out waiting for fork '{fork_full_name}' to be created"
    )


def _create_branch(
    fork_repo: str,
    branch_name: str,
    token: str,
) -> str:
    """Create a new branch on the fork from the default branch HEAD.

    Args:
        fork_repo: Fork repo in ``owner/name`` format.
        branch_name: Name of the new branch.
        token: GitHub personal access token.

    Returns:
        SHA of the branch head.

    Raises:
        PublishError: If branch creation fails.
    """
    # Get the SHA of the default branch
    ref_data = _github_request(
        "GET",
        f"{_GITHUB_API_BASE}/repos/{fork_repo}/git/ref/heads/main",
        token,
    )
    base_sha = ref_data["object"]["sha"]

    # Create the branch
    _github_request(
        "POST",
        f"{_GITHUB_API_BASE}/repos/{fork_repo}/git/refs",
        token,
        data={
            "ref": f"refs/heads/{branch_name}",
            "sha": base_sha,
        },
    )

    return base_sha


def _upload_manifest(
    fork_repo: str,
    branch_name: str,
    file_path: str,
    content: bytes,
    token: str,
    package_name: str,
    package_version: str,
) -> None:
    """Upload the manifest file to the fork.

    Uses the GitHub Contents API to create or update the file on the
    specified branch.

    Args:
        fork_repo: Fork repo in ``owner/name`` format.
        branch_name: Branch to commit to.
        file_path: Path within the repo (e.g.
            ``manifests/python/r/requests/2.31.0.lcp.json.gz``).
        content: Gzip-compressed manifest bytes.
        token: GitHub personal access token.
        package_name: Package name (for commit message).
        package_version: Package version (for commit message).

    Raises:
        PublishError: If file upload fails.
    """
    encoded_content = base64.b64encode(content).decode("ascii")

    _github_request(
        "PUT",
        f"{_GITHUB_API_BASE}/repos/{fork_repo}/contents/{file_path}",
        token,
        data={
            "message": f"Add {package_name} v{package_version} LCP manifest",
            "content": encoded_content,
            "branch": branch_name,
        },
    )


def _build_pr_body(
    document: LCPDocument,
    manifest_path: str,
    lcp_version: str,
) -> str:
    """Build a structured PR body for the manifest submission.

    Args:
        document: The LCP document being published.
        manifest_path: Path of the manifest in the registry repo.
        lcp_version: Version of the lcp SDK.

    Returns:
        Markdown-formatted PR body.
    """
    lib = document.manifest.library
    symbol_count = len(document.symbols)

    lines = [
        "## New Manifest Submission",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Package | {lib.name} |",
        f"| Version | {lib.version} |",
        f"| Language | {lib.language} |",
        f"| Symbols | {symbol_count} |",
        f"| Schema Version | {document.manifest.schema_version} |",
        "",
        "### Manifest Path",
        "",
        f"`{manifest_path}`",
        "",
        "### Labels",
        "",
        f"`new_manifest`, `{lib.language}`",
        "",
        "### Generation Details",
        "",
        f"- **Tool:** lcp Python SDK v{lcp_version}",
        f"- **Schema Version:** {document.manifest.schema_version}",
        "",
        "### Checklist",
        "",
        "- [x] Manifest generated from installed package",
        "- [x] Manifest validated against LCP schema",
        "- [x] File placed in correct registry path",
    ]
    return "\n".join(lines)


def _create_pull_request(
    registry_repo: str,
    fork_repo: str,
    branch_name: str,
    package_name: str,
    package_version: str,
    language: str,
    pr_body: str,
    token: str,
) -> dict:
    """Create a pull request from the fork branch to the registry main.

    Args:
        registry_repo: Upstream registry repo in ``owner/name`` format.
        fork_repo: Fork repo in ``owner/name`` format.
        branch_name: Branch name on the fork.
        package_name: Package name (for PR title).
        package_version: Package version (for PR title).
        language: Programming language (for PR title and labels).
        pr_body: Markdown body for the PR.
        token: GitHub personal access token.

    Returns:
        GitHub API response dict for the created PR.

    Raises:
        PublishError: If PR creation fails.
    """
    fork_owner = fork_repo.split("/")[0]
    title = f"[new_manifest] Add {package_name} v{package_version} ({language})"

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

    return pr_data


def _try_add_labels(
    registry_repo: str,
    pr_number: int,
    labels: list[str],
    token: str,
) -> None:
    """Attempt to add labels to the PR.

    This may fail if the user does not have write access to the
    upstream repository.  Failures are silently ignored.

    Args:
        registry_repo: Upstream registry repo in ``owner/name`` format.
        pr_number: PR number to label.
        labels: List of label names.
        token: GitHub personal access token.
    """
    try:
        _github_request(
            "POST",
            f"{_GITHUB_API_BASE}/repos/{registry_repo}/issues/{pr_number}/labels",
            token,
            data={"labels": labels},
        )
    except PublishError:
        pass  # User may not have permission to add labels


def publish_manifest(
    document: LCPDocument,
    token: str,
    registry_repo: str = _DEFAULT_REGISTRY_REPO,
) -> PublishResult:
    """Publish an LCP manifest to the registry via GitHub Pull Request.

    This function performs the full publish workflow:

    1. Authenticates with GitHub using the provided token
    2. Forks the registry repository (if not already forked)
    3. Creates a branch for the new manifest
    4. Uploads the manifest file to the correct registry path
    5. Opens a pull request with structured content and labels

    Args:
        document: Validated LCP document to publish.
        token: GitHub personal access token with ``repo`` or
            ``public_repo`` scope.
        registry_repo: Registry repository in ``owner/name`` format
            (default: ``zazza123/lcp-registry``).

    Returns:
        ``PublishResult`` with the PR URL and metadata.

    Raises:
        PublishError: If any step of the publish workflow fails.
        ValueError: If the registry repo format is invalid.
    """
    # Validate registry repo format
    if "/" not in registry_repo or registry_repo.count("/") != 1:
        raise ValueError(
            f"Invalid registry repo format: '{registry_repo}'. "
            "Expected 'owner/name'."
        )

    lib = document.manifest.library
    name = lib.name
    version = lib.version
    language = lib.language

    # Prevent path traversal in package name
    if ".." in name or "/" in name or "\\" in name:
        raise PublishError(f"Invalid package name: '{name}'")

    manifest_path = f"manifests/{language}/{name[0].lower()}/{name}/{version}.lcp.json.gz"
    branch_name = f"lcp/add/{name}/{version}"

    from . import __version__ as lcp_version

    # Step 1: Authenticate and get username
    username = _get_authenticated_user(token)

    # Step 2: Fork the registry repo
    fork_repo = _ensure_fork(username, registry_repo, token)

    # Step 3: Create a branch
    _create_branch(fork_repo, branch_name, token)

    # Step 4: Upload the manifest (gzip-compressed)
    manifest_bytes = gzip.compress(document.to_json(indent=2).encode("utf-8"))
    _upload_manifest(
        fork_repo,
        branch_name,
        manifest_path,
        manifest_bytes,
        token,
        name,
        version,
    )

    # Step 5: Create the PR
    pr_body = _build_pr_body(document, manifest_path, lcp_version)
    pr_data = _create_pull_request(
        registry_repo,
        fork_repo,
        branch_name,
        name,
        version,
        language,
        pr_body,
        token,
    )

    pr_url = pr_data.get("html_url", "")
    pr_number = pr_data.get("number", 0)

    # Step 6: Try to add labels (best-effort)
    labels = _PR_LABELS + [language]
    _try_add_labels(registry_repo, pr_number, labels, token)

    return PublishResult(
        pr_url=pr_url,
        pr_number=pr_number,
        manifest_path=manifest_path,
        package_name=name,
        package_version=version,
        language=language,
    )
