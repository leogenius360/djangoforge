"""
Tests for core utilities and security functions.
"""

import warnings

from django.db import models

from apps.core.security import constant_time_compare, generate_fingerprint, generate_secure_token
from apps.core.security.crypto import generate_secure_hash
from apps.core.utils import model_has_field


class TestModelFieldSupport:
    """Tests for model field existence checking."""

    def test_model_has_field_true(self):
        """Test model_has_field returns True for existing fields."""

        class TestModelHasFieldTrue(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "core"

            def __str__(self) -> str:
                return self.name

        assert model_has_field(TestModelHasFieldTrue, "name") is True
        assert model_has_field(TestModelHasFieldTrue, "id") is True

    def test_model_has_field_false(self):
        """Test model_has_field returns False for non-existent fields."""

        class TestModelHasFieldFalse(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "core"

            def __str__(self) -> str:
                return self.name

        assert model_has_field(TestModelHasFieldFalse, "nonexistent") is False

    def test_model_has_field_caching(self):
        """Test that field existence checks are cached per model."""

        class TestModelHasFieldCaching(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "core"

            def __str__(self) -> str:
                return self.name

        # First call
        result1 = model_has_field(TestModelHasFieldCaching, "name")

        # Second call should use cached value (lru_cache)
        result2 = model_has_field(TestModelHasFieldCaching, "name")

        # Both results should be True and identical (cached)
        assert result1 is True
        assert result2 is True
        assert result1 == result2


class TestSecurityUtilities:
    """Tests for security and crypto utilities."""

    def test_generate_secure_token(self):
        """Test secure token generation."""
        token1 = generate_secure_token()
        token2 = generate_secure_token()

        # Tokens should be unique
        assert token1 != token2

        # Tokens should be strings
        assert isinstance(token1, str)
        assert isinstance(token2, str)

        # Length should be reasonable (base64 encoded)
        assert len(token1) > 20

    def test_generate_secure_token_custom_length(self):
        """Test secure token generation with custom length."""
        token = generate_secure_token(length=16)
        assert isinstance(token, str)
        # Note: URL-safe base64 encoding may produce longer strings than input bytes

    def test_generate_fingerprint(self):
        """Test fingerprint generation."""
        data = "test data"
        fingerprint1 = generate_fingerprint(data)
        fingerprint2 = generate_fingerprint(data)

        # Same data should produce same fingerprint
        assert fingerprint1 == fingerprint2

        # Fingerprint should be hex string
        assert isinstance(fingerprint1, str)
        assert len(fingerprint1) == 64  # SHA-256 produces 64 hex chars

        # Different data should produce different fingerprints
        different_fingerprint = generate_fingerprint("different data")
        assert fingerprint1 != different_fingerprint

    def test_generate_fingerprint_deterministic(self):
        """Test that fingerprints are deterministic."""
        data = "consistent data"
        expected = generate_fingerprint(data)

        # Multiple calls should produce same result
        for _ in range(5):
            assert generate_fingerprint(data) == expected

    def test_generate_secure_hash_deprecated(self):
        """Test that generate_secure_hash raises deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            result = generate_secure_hash("test")

            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

        # Should still work but is deprecated
        assert isinstance(result, str)
        assert len(result) == 64

    def test_generate_secure_hash_with_salt_deprecated(self):
        """Test generate_secure_hash with salt (deprecated functionality)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            result1 = generate_secure_hash("test", salt="salt1")
            result2 = generate_secure_hash("test", salt="salt2")

            # Different salts should produce different results
            assert result1 != result2
            assert len(w) == 2  # Two deprecation warnings

    def test_constant_time_compare_equal(self):
        """Test constant-time comparison with equal strings."""
        assert constant_time_compare("secret", "secret") is True
        assert constant_time_compare("", "") is True
        assert constant_time_compare("a" * 100, "a" * 100) is True

    def test_constant_time_compare_not_equal(self):
        """Test constant-time comparison with different strings."""
        assert constant_time_compare("secret", "Secret") is False
        assert constant_time_compare("abc", "def") is False
        assert constant_time_compare("short", "longer_string") is False
        assert constant_time_compare("", "nonempty") is False
