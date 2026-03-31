"""Tests for the publish module."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from lcp.models import LCPDocument, Library, Manifest, Symbol, Semantics
from lcp.publish import (
    PublishError,
    PublishResult,
    _build_pr_body,
    _create_branch,
    _create_pull_request,
    _ensure_fork,
    _get_authenticated_user,
    _github_request,
    _try_add_labels,
    _upload_manifest,
    publish_manifest,
    _DEFAULT_REGISTRY_REPO,
    _GITHUB_API_BASE,
)


@pytest.fixture
def sample_document():
    """Create a minimal valid LCPDocument for testing."""
    return LCPDocument(
        manifest=Manifest(
            schema_version="1.0",
            library=Library(name="mylib", version="1.0.0", language="python"),
        ),
        symbols={
            "mylib:func_a": Symbol(
                kind="function",
                semantics=Semantics(summary="Function A."),
            ),
            "mylib:func_b": Symbol(
                kind="function",
                semantics=Semantics(summary="Function B."),
            ),
        },
    )


@pytest.fixture
def mock_token():
    """Return a fake GitHub token."""
    return "ghp_test_token_123"


class TestGitHubRequest:
    """Tests for _github_request."""

    @patch("lcp.publish.urllib.request.urlopen")
    def test_get_request(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"login": "testuser"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = _github_request("GET", f"{_GITHUB_API_BASE}/user", "fake_token")
        assert result == {"login": "testuser"}

    @patch("lcp.publish.urllib.request.urlopen")
    def test_post_request_with_data(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"id": 1}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = _github_request(
            "POST", f"{_GITHUB_API_BASE}/repos/test/forks", "fake_token",
            data={"key": "value"},
        )
        assert result == {"id": 1}

        # Verify the request was constructed with data
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.data is not None
        assert req.get_method() == "POST"

    @patch("lcp.publish.urllib.request.urlopen")
    def test_empty_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b""
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = _github_request("POST", f"{_GITHUB_API_BASE}/test", "fake_token")
        assert result == {}

    @patch("lcp.publish.urllib.request.urlopen")
    def test_401_unauthorized(self, mock_urlopen):
        import urllib.error

        exc = urllib.error.HTTPError(
            url="http://example.com", code=401, msg="Unauthorized",
            hdrs=None, fp=MagicMock(read=MagicMock(return_value=b"")),
        )
        mock_urlopen.side_effect = exc

        with pytest.raises(PublishError, match="Invalid or expired GitHub token"):
            _github_request("GET", f"{_GITHUB_API_BASE}/user", "bad_token")

    @patch("lcp.publish.urllib.request.urlopen")
    def test_403_forbidden(self, mock_urlopen):
        import urllib.error

        exc = urllib.error.HTTPError(
            url="http://example.com", code=403, msg="Forbidden",
            hdrs=None, fp=MagicMock(read=MagicMock(return_value=b"")),
        )
        mock_urlopen.side_effect = exc

        with pytest.raises(PublishError, match="lacks required permissions"):
            _github_request("GET", f"{_GITHUB_API_BASE}/user", "bad_token")

    @patch("lcp.publish.urllib.request.urlopen")
    def test_other_http_error(self, mock_urlopen):
        import urllib.error

        error_body = json.dumps({"message": "Not Found"}).encode()
        exc = urllib.error.HTTPError(
            url="http://example.com", code=404, msg="Not Found",
            hdrs=None, fp=MagicMock(read=MagicMock(return_value=error_body)),
        )
        mock_urlopen.side_effect = exc

        with pytest.raises(PublishError, match="HTTP 404"):
            _github_request("GET", f"{_GITHUB_API_BASE}/test", "fake_token")

    @patch("lcp.publish.urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with pytest.raises(PublishError, match="Network error"):
            _github_request("GET", f"{_GITHUB_API_BASE}/user", "fake_token")

    @patch("lcp.publish.urllib.request.urlopen")
    def test_timeout_error(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError()

        with pytest.raises(PublishError, match="timed out"):
            _github_request("GET", f"{_GITHUB_API_BASE}/user", "fake_token")


class TestGetAuthenticatedUser:
    """Tests for _get_authenticated_user."""

    @patch("lcp.publish._github_request")
    def test_returns_username(self, mock_request):
        mock_request.return_value = {"login": "testuser"}
        assert _get_authenticated_user("token") == "testuser"

    @patch("lcp.publish._github_request")
    def test_missing_login(self, mock_request):
        mock_request.return_value = {}
        with pytest.raises(PublishError, match="Could not determine GitHub username"):
            _get_authenticated_user("token")


class TestEnsureFork:
    """Tests for _ensure_fork."""

    @patch("lcp.publish._github_request")
    def test_fork_exists(self, mock_request):
        mock_request.return_value = {"full_name": "testuser/lcp-registry"}
        result = _ensure_fork("testuser", "zazza123/lcp-registry", "token")
        assert result == "testuser/lcp-registry"

    @patch("lcp.publish.time.sleep")
    @patch("lcp.publish._github_request")
    def test_creates_fork(self, mock_request, mock_sleep):
        # First call: fork doesn't exist (GET raises error)
        # Second call: create fork (POST succeeds)
        # Third call: poll fork (GET succeeds)
        call_count = [0]

        def side_effect(method, url, token, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Fork doesn't exist
                raise PublishError("Not found")
            if call_count[0] == 2:
                # Create fork
                return {"full_name": "testuser/lcp-registry"}
            # Poll - fork ready
            return {"full_name": "testuser/lcp-registry"}

        mock_request.side_effect = side_effect
        result = _ensure_fork("testuser", "zazza123/lcp-registry", "token")
        assert result == "testuser/lcp-registry"

    @patch("lcp.publish.time.sleep")
    @patch("lcp.publish._github_request")
    def test_fork_timeout(self, mock_request, mock_sleep):
        def side_effect(method, url, token, **kwargs):
            if method == "POST":
                return {}
            raise PublishError("Not found")

        mock_request.side_effect = side_effect
        with pytest.raises(PublishError, match="Timed out"):
            _ensure_fork("testuser", "zazza123/lcp-registry", "token")


class TestCreateBranch:
    """Tests for _create_branch."""

    @patch("lcp.publish._github_request")
    def test_creates_branch(self, mock_request):
        mock_request.side_effect = [
            {"object": {"sha": "abc123"}},  # GET ref
            {"ref": "refs/heads/lcp/add/test/1.0.0"},  # POST ref
        ]
        sha = _create_branch("testuser/lcp-registry", "lcp/add/test/1.0.0", "token")
        assert sha == "abc123"
        assert mock_request.call_count == 2


class TestUploadManifest:
    """Tests for _upload_manifest."""

    @patch("lcp.publish._github_request")
    def test_uploads_file(self, mock_request):
        import gzip

        mock_request.return_value = {"content": {"sha": "def456"}}
        content_bytes = gzip.compress(b'{"test": true}')
        _upload_manifest(
            "testuser/lcp-registry",
            "lcp/add/test/1.0.0",
            "manifests/python/t/test/1.0.0.lcp.json.gz",
            content_bytes,
            "token",
            "test",
            "1.0.0",
        )
        assert mock_request.call_count == 1

        # Verify the content is base64-encoded gzip bytes
        call_args = mock_request.call_args
        data = call_args[1]["data"] if "data" in call_args[1] else call_args[0][3]
        encoded = base64.b64encode(content_bytes).decode("ascii")
        assert data["content"] == encoded
        assert data["branch"] == "lcp/add/test/1.0.0"


class TestBuildPrBody:
    """Tests for _build_pr_body."""

    def test_structured_body(self, sample_document):
        body = _build_pr_body(
            sample_document,
            "manifests/python/m/mylib/1.0.0.lcp.json.gz",
            "0.1.0",
        )
        assert "## New Manifest Submission" in body
        assert "| Package | mylib |" in body
        assert "| Version | 1.0.0 |" in body
        assert "| Language | python |" in body
        assert "| Symbols | 2 |" in body
        assert "`manifests/python/m/mylib/1.0.0.lcp.json.gz`" in body
        assert "`new_manifest`, `python`" in body
        assert "lcp Python SDK v0.1.0" in body
        assert "- [x] Manifest generated from installed package" in body
        assert "- [x] Manifest validated against LCP schema" in body


class TestCreatePullRequest:
    """Tests for _create_pull_request."""

    @patch("lcp.publish._github_request")
    def test_creates_pr(self, mock_request):
        mock_request.return_value = {
            "html_url": "https://github.com/zazza123/lcp-registry/pull/42",
            "number": 42,
        }
        result = _create_pull_request(
            "zazza123/lcp-registry",
            "testuser/lcp-registry",
            "lcp/add/mylib/1.0.0",
            "mylib",
            "1.0.0",
            "python",
            "PR body",
            "token",
        )
        assert result["number"] == 42
        assert "pull/42" in result["html_url"]

        # Verify PR data
        call_args = mock_request.call_args
        data = call_args[1]["data"] if "data" in call_args[1] else call_args[0][3]
        assert data["title"] == "[new_manifest] Add mylib v1.0.0 (python)"
        assert data["head"] == "testuser:lcp/add/mylib/1.0.0"
        assert data["base"] == "main"


class TestTryAddLabels:
    """Tests for _try_add_labels."""

    @patch("lcp.publish._github_request")
    def test_adds_labels(self, mock_request):
        mock_request.return_value = [{"name": "new_manifest"}, {"name": "python"}]
        _try_add_labels("zazza123/lcp-registry", 42, ["new_manifest", "python"], "token")
        assert mock_request.call_count == 1

    @patch("lcp.publish._github_request")
    def test_silently_ignores_permission_error(self, mock_request):
        mock_request.side_effect = PublishError("Forbidden")
        # Should not raise
        _try_add_labels("zazza123/lcp-registry", 42, ["new_manifest"], "token")


class TestPublishManifest:
    """Tests for publish_manifest (end-to-end with mocks)."""

    @patch("lcp.publish._try_add_labels")
    @patch("lcp.publish._create_pull_request")
    @patch("lcp.publish._upload_manifest")
    @patch("lcp.publish._create_branch")
    @patch("lcp.publish._ensure_fork")
    @patch("lcp.publish._get_authenticated_user")
    def test_full_workflow(
        self,
        mock_get_user,
        mock_fork,
        mock_branch,
        mock_upload,
        mock_pr,
        mock_labels,
        sample_document,
        mock_token,
    ):
        mock_get_user.return_value = "testuser"
        mock_fork.return_value = "testuser/lcp-registry"
        mock_branch.return_value = "abc123"
        mock_pr.return_value = {
            "html_url": "https://github.com/zazza123/lcp-registry/pull/1",
            "number": 1,
        }

        result = publish_manifest(sample_document, mock_token)

        assert isinstance(result, PublishResult)
        assert result.pr_url == "https://github.com/zazza123/lcp-registry/pull/1"
        assert result.pr_number == 1
        assert result.manifest_path == "manifests/python/m/mylib/1.0.0.lcp.json.gz"
        assert result.package_name == "mylib"
        assert result.package_version == "1.0.0"
        assert result.language == "python"

        # Verify the correct sequence of calls
        mock_get_user.assert_called_once_with(mock_token)
        mock_fork.assert_called_once_with("testuser", _DEFAULT_REGISTRY_REPO, mock_token)
        mock_branch.assert_called_once()
        mock_upload.assert_called_once()
        mock_pr.assert_called_once()
        mock_labels.assert_called_once()

    def test_invalid_registry_repo_format(self, sample_document, mock_token):
        with pytest.raises(ValueError, match="Invalid registry repo format"):
            publish_manifest(sample_document, mock_token, registry_repo="invalid")

    def test_invalid_package_name_path_traversal(self, mock_token):
        doc = LCPDocument(
            manifest=Manifest(
                schema_version="1.0",
                library=Library(name="../evil", version="1.0.0", language="python"),
            ),
            symbols={},
        )
        with pytest.raises(PublishError, match="Invalid package name"):
            publish_manifest(doc, mock_token)

    @patch("lcp.publish._try_add_labels")
    @patch("lcp.publish._create_pull_request")
    @patch("lcp.publish._upload_manifest")
    @patch("lcp.publish._create_branch")
    @patch("lcp.publish._ensure_fork")
    @patch("lcp.publish._get_authenticated_user")
    def test_custom_registry_repo(
        self,
        mock_get_user,
        mock_fork,
        mock_branch,
        mock_upload,
        mock_pr,
        mock_labels,
        sample_document,
        mock_token,
    ):
        mock_get_user.return_value = "testuser"
        mock_fork.return_value = "testuser/custom-registry"
        mock_branch.return_value = "abc123"
        mock_pr.return_value = {"html_url": "", "number": 5}

        result = publish_manifest(
            sample_document,
            mock_token,
            registry_repo="custom-org/custom-registry",
        )
        assert result.pr_number == 5
        mock_fork.assert_called_once_with(
            "testuser", "custom-org/custom-registry", mock_token
        )

    @patch("lcp.publish._try_add_labels")
    @patch("lcp.publish._create_pull_request")
    @patch("lcp.publish._upload_manifest")
    @patch("lcp.publish._create_branch")
    @patch("lcp.publish._ensure_fork")
    @patch("lcp.publish._get_authenticated_user")
    def test_labels_include_language(
        self,
        mock_get_user,
        mock_fork,
        mock_branch,
        mock_upload,
        mock_pr,
        mock_labels,
        mock_token,
    ):
        doc = LCPDocument(
            manifest=Manifest(
                schema_version="1.0",
                library=Library(name="mylib", version="1.0.0", language="javascript"),
            ),
            symbols={},
        )
        mock_get_user.return_value = "testuser"
        mock_fork.return_value = "testuser/lcp-registry"
        mock_branch.return_value = "abc123"
        mock_pr.return_value = {"html_url": "", "number": 10}

        result = publish_manifest(doc, mock_token)
        assert result.language == "javascript"

        # Verify labels include "new_manifest" and the language
        mock_labels.assert_called_once_with(
            _DEFAULT_REGISTRY_REPO, 10, ["new_manifest", "javascript"], mock_token
        )

    @patch("lcp.publish._try_add_labels")
    @patch("lcp.publish._create_pull_request")
    @patch("lcp.publish._create_branch")
    @patch("lcp.publish._ensure_fork")
    @patch("lcp.publish._get_authenticated_user")
    def test_upload_uses_gzip_and_sharded_path(
        self,
        mock_get_user,
        mock_fork,
        mock_branch,
        mock_pr,
        mock_labels,
        sample_document,
        mock_token,
    ):
        """publish_manifest should compress the manifest and use a sharded .gz path."""
        import gzip

        mock_get_user.return_value = "testuser"
        mock_fork.return_value = "testuser/lcp-registry"
        mock_branch.return_value = "abc123"
        mock_pr.return_value = {"html_url": "", "number": 99}

        captured_calls = []

        def capture_upload(*args, **kwargs):
            captured_calls.append((args, kwargs))

        with patch("lcp.publish._upload_manifest", side_effect=capture_upload):
            publish_manifest(sample_document, mock_token)

        assert len(captured_calls) == 1
        args, _ = captured_calls[0]
        file_path = args[2]
        content = args[3]

        # Path must use sharding (first letter) and .gz extension
        assert file_path == "manifests/python/m/mylib/1.0.0.lcp.json.gz"

        # Content must be valid gzip-compressed JSON
        assert isinstance(content, bytes)
        decompressed = gzip.decompress(content)
        import json
        data = json.loads(decompressed)
        assert data["manifest"]["library"]["name"] == "mylib"
