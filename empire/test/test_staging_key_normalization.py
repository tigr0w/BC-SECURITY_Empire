"""Tests for staging key SHA-256 normalization (FIPS compliance)."""

import hashlib
from types import SimpleNamespace

import pytest

from empire.server.core.listener_service import ListenerService


class TestStagingKeyNormalization:
    def test_short_key_normalized_to_sha256(self):
        """A non-32-char key should be replaced with its SHA-256 hex[:32]."""
        instance = SimpleNamespace(options={"StagingKey": {"Value": "mykey"}})
        ListenerService._normalize_listener_options(instance)
        expected = hashlib.sha256(b"mykey").hexdigest()[:32]
        assert instance.options["StagingKey"]["Value"] == expected
        assert len(instance.options["StagingKey"]["Value"]) == 32  # noqa: PLR2004

    def test_32_char_key_unchanged(self):
        """An exactly 32-char key should pass through as-is."""
        key = "2c103f2c4ed1e59c0b4e2e01821770fa"
        instance = SimpleNamespace(options={"StagingKey": {"Value": key}})
        ListenerService._normalize_listener_options(instance)
        assert instance.options["StagingKey"]["Value"] == key

    def test_whitespace_stripped_before_check(self):
        """Leading/trailing whitespace should be stripped before length check."""
        instance = SimpleNamespace(options={"StagingKey": {"Value": "  mykey  "}})
        ListenerService._normalize_listener_options(instance)
        expected = hashlib.sha256(b"mykey").hexdigest()[:32]
        assert instance.options["StagingKey"]["Value"] == expected

    def test_long_key_normalized(self):
        """A key longer than 32 chars should also be normalized."""
        long_key = "a" * 64
        instance = SimpleNamespace(options={"StagingKey": {"Value": long_key}})
        ListenerService._normalize_listener_options(instance)
        expected = hashlib.sha256(long_key.encode("UTF-8")).hexdigest()[:32]
        assert instance.options["StagingKey"]["Value"] == expected

    def test_output_is_lowercase_hex(self):
        """Normalized key must be lowercase hex."""
        instance = SimpleNamespace(options={"StagingKey": {"Value": "test"}})
        ListenerService._normalize_listener_options(instance)
        result = instance.options["StagingKey"]["Value"]
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    def test_not_md5(self):
        """Verify the output is SHA-256, not the old MD5 algorithm."""
        instance = SimpleNamespace(options={"StagingKey": {"Value": "mykey"}})
        ListenerService._normalize_listener_options(instance)
        md5_result = hashlib.md5(b"mykey").hexdigest()
        assert instance.options["StagingKey"]["Value"] != md5_result

    def test_empty_key_rejected(self):
        """Empty staging key should raise ValueError."""
        instance = SimpleNamespace(options={"StagingKey": {"Value": ""}})
        with pytest.raises(ValueError, match="StagingKey cannot be empty"):
            ListenerService._normalize_listener_options(instance)

    def test_whitespace_only_key_rejected(self):
        """Whitespace-only staging key should raise ValueError after strip."""
        instance = SimpleNamespace(options={"StagingKey": {"Value": "   "}})
        with pytest.raises(ValueError, match="StagingKey cannot be empty"):
            ListenerService._normalize_listener_options(instance)
