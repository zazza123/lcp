"""Tests for package name normalization."""

from __future__ import annotations

import pytest

from lcp.naming import normalize_package_name


class TestNormalizePackageName:
    """Tests for normalize_package_name."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("google.adk", "google-adk"),
            ("Google.ADK", "google-adk"),
            ("azure.ai.contentunderstanding", "azure-ai-contentunderstanding"),
            ("requests", "requests"),
            ("my_package", "my-package"),
            ("My-Package", "my-package"),
            ("a..b", "a-b"),
            ("a__b", "a-b"),
            ("a-_.b", "a-b"),
        ],
    )
    def test_normalization(self, raw, expected):
        assert normalize_package_name(raw) == expected

    def test_already_normalized_is_stable(self):
        """Normalizing an already-normalized slug is a no-op."""
        assert normalize_package_name("google-adk") == "google-adk"
