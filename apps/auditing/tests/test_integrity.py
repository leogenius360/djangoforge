"""
Tests for audit integrity utilities.
"""

import pytest

from apps.auditing.utils import IntegrityService, IntegrityVerificationError


class TestIntegrityService:
    """Test suite for IntegrityService."""

    def test_initialization_defaults(self):
        """Test service initializes with correct defaults."""
        service = IntegrityService()
        assert service.algorithm == "sha256"

    def test_initialization_custom(self):
        """Test service initializes with custom algorithm."""
        service = IntegrityService(algorithm="sha512")
        assert service.algorithm == "sha512"

    def test_hash_returns_result(self):
        """Test hash returns HashResult."""
        service = IntegrityService()
        data = {"key": "value", "number": 123}

        result = service.hash(data)
        assert result.digest
        assert len(result.digest) == 64  # SHA-256 is 64 hex chars
        assert result.algorithm == "sha256"
        assert result.input_size > 0

    def test_hash_simple_returns_string(self):
        """Test hash_simple returns just the digest."""
        service = IntegrityService()
        data = {"key": "value"}

        digest = service.hash_simple(data)
        assert isinstance(digest, str)
        assert len(digest) == 64

    def test_hash_empty_state_returns_empty(self):
        """Test hashing None or empty returns empty string."""
        service = IntegrityService()

        result = service.hash(None)
        assert result.digest == ""
        assert result.input_size == 0

    def test_hash_deterministic(self):
        """Test that same data always produces same hash."""
        service = IntegrityService()
        data = {"key": "value", "number": 123}

        hash1 = service.hash_simple(data)
        hash2 = service.hash_simple(data)
        assert hash1 == hash2

    def test_hash_order_independent(self):
        """Test that key order doesn't affect hash (canonical JSON)."""
        service = IntegrityService()
        data1 = {"a": 1, "b": 2, "c": 3}
        data2 = {"c": 3, "b": 2, "a": 1}

        hash1 = service.hash_simple(data1)
        hash2 = service.hash_simple(data2)
        assert hash1 == hash2

    def test_verify_valid(self):
        """Test verifying valid state passes."""
        service = IntegrityService()
        data = {"key": "value"}

        expected_hash = service.hash_simple(data)
        assert service.verify(data, expected_hash)

    def test_verify_invalid(self):
        """Test verifying tampered state fails."""
        service = IntegrityService()
        data = {"key": "value"}
        tampered_data = {"key": "tampered"}

        expected_hash = service.hash_simple(data)
        assert not service.verify(tampered_data, expected_hash)

    def test_verify_raise_on_mismatch(self):
        """Test verify raises exception when raise_on_mismatch=True."""
        service = IntegrityService()
        data = {"key": "value"}
        tampered_data = {"key": "tampered"}

        expected_hash = service.hash_simple(data)
        with pytest.raises(IntegrityVerificationError, match="integrity verification failed"):
            service.verify(tampered_data, expected_hash, raise_on_mismatch=True)

    def test_verify_no_hash_returns_true(self):
        """Test that verification with no hash returns True."""
        service = IntegrityService()
        data = {"key": "value"}

        # No hash to verify against
        assert service.verify(data, "")

    def test_hash_event_payload(self):
        """Test hashing event payload."""
        service = IntegrityService()
        event_data = {"event": "update", "timestamp": "2024-01-01"}

        result = service.hash_event_payload(event_data)
        assert result.digest
        assert result.algorithm == "sha256"

    def test_hash_event_payload_with_parent_hash(self):
        """Test hashing event payload with previous hash included."""
        service = IntegrityService()
        event_data = {"event": "update"}
        previous_hash = "abc123"

        result = service.hash_event_payload(event_data, parent_checksum=previous_hash)
        assert result.digest

        # Should be different from hash without parent hash
        result_without = service.hash_event_payload(event_data)
        assert result.digest != result_without.digest

    def test_verify_event_chain_valid(self):
        """Test event chain verification with valid chain."""
        service = IntegrityService()
        event_data = {"event": "update", "field": "value"}
        previous_hash = "abc123"

        # Compute hash with parent hash included
        result = service.hash_event_payload(event_data, parent_checksum=previous_hash)

        # Verify chain
        assert service.verify_event_chain(
            event_data,
            result.digest,
            previous_hash,
        )

    def test_verify_event_chain_invalid(self):
        """Test event chain verification with broken chain."""
        service = IntegrityService()
        event_data = {"event": "update"}
        previous_hash = "abc123"
        wrong_hash = "xyz789"

        # Should fail
        assert not service.verify_event_chain(
            event_data,
            wrong_hash,
            previous_hash,
        )

    def test_verify_event_chain_raise_on_mismatch(self):
        """Test event chain verification raises on invalid chain."""
        service = IntegrityService()
        event_data = {"event": "update"}
        previous_hash = "abc123"
        wrong_hash = "xyz789"

        with pytest.raises(IntegrityVerificationError, match="Event chain verification failed"):
            service.verify_event_chain(
                event_data,
                wrong_hash,
                previous_hash,
                raise_on_mismatch=True,
            )

    def test_compute_batch_hash(self):
        """Test computing hash for batch of states."""
        service = IntegrityService()
        states = [
            {"id": 1, "name": "first"},
            {"id": 2, "name": "second"},
            {"id": 3, "name": "third"},
        ]

        result = service.hash(states)
        assert result.digest
        assert result.algorithm == "sha256"

    def test_compute_batch_hash_empty(self):
        """Test batch hash with empty list."""
        service = IntegrityService()

        result = service.hash(None)
        assert result.digest == ""
        assert result.input_size == 0

    def test_sha512_algorithm(self):
        """Test SHA-512 algorithm."""
        service = IntegrityService(algorithm="sha512")
        data = {"key": "value"}

        result = service.hash(data)
        assert result.algorithm == "sha512"
        assert len(result.digest) == 128  # SHA-512 is 128 hex chars
