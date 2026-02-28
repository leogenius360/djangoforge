"""
Tests for audit compression utilities.
"""

import pytest
from django.test import override_settings

from apps.auditing.utils import CompressionError, CompressionService


class TestCompressionService:
    """Test suite for CompressionService."""

    def test_initialization_defaults(self):
        """Test service initializes with correct defaults."""
        service = CompressionService()
        assert service.algorithm == "zlib"
        assert service.level == 6
        # Default threshold comes from audit_settings.COMPRESSION_THRESHOLD which is 1024
        assert service.threshold == 1024

    def test_initialization_custom(self):
        """Test service initializes with custom settings."""
        service = CompressionService(algorithm="gzip", level=9, threshold=5000)
        assert service.algorithm == "gzip"
        assert service.level == 9
        assert service.threshold == 5000

    def test_invalid_algorithm_raises_error(self):
        """Test that invalid algorithm raises CompressionError."""
        with pytest.raises(CompressionError, match="Invalid compression algorithm"):
            CompressionService(algorithm="invalid")

    def test_invalid_level_for_zlib_raises_error(self):
        """Test that invalid compression level raises error."""
        with pytest.raises(CompressionError, match="Invalid compression level"):
            CompressionService(algorithm="zlib", level=10)

    def test_should_compress_small_data(self):
        """Test that small data is not compressed."""
        service = CompressionService(threshold=1000)
        data = {"key": "value"}
        assert not service.should_compress(data)

    def test_should_compress_large_data(self):
        """Test that large data is compressed when COMPRESSION_ENABLED is True."""
        service = CompressionService(threshold=100)
        data = {"key": "x" * 1000}
        with override_settings(AUDITING={"COMPRESSION_ENABLED": True}):
            assert service.should_compress(data)

    def test_compress_and_decompress_roundtrip(self):
        """Test compress and decompress round trip."""
        service = CompressionService()
        data = {"name": "test", "value": 123, "nested": {"key": "val"}}

        result = service.compress(data)
        assert result.original_size > 0
        assert result.compressed_size > 0
        assert result.algorithm == "zlib"

        decompressed = service.decompress(result.compressed_data)
        assert decompressed == data

    def test_compress_empty_data_raises_error(self):
        """Test that compressing empty data raises error."""
        service = CompressionService()
        with pytest.raises(CompressionError, match="Cannot compress empty data"):
            service.compress({})

    def test_decompress_empty_data_raises_error(self):
        """Test that decompressing empty data raises error."""
        service = CompressionService()
        with pytest.raises(CompressionError, match="Cannot decompress empty data"):
            service.decompress(b"")

    def test_compress_and_encode_for_json_storage(self):
        """Test compress and encode for JSON storage."""
        service = CompressionService()
        data = {"test": "data" * 100}

        encoded, result = service.compress_and_encode(data)
        assert isinstance(encoded, str)
        assert result.original_size > 0

        # Decode and decompress
        decompressed = service.decode_and_decompress(encoded)
        assert decompressed == data

    def test_gzip_compression(self):
        """Test gzip compression algorithm."""
        service = CompressionService(algorithm="gzip")
        data = {"key": "value" * 100}

        result = service.compress(data)
        assert result.algorithm == "gzip"

        decompressed = service.decompress(result.compressed_data)
        assert decompressed == data

    def test_no_compression_algorithm(self):
        """Test that 'none' algorithm doesn't compress."""
        service = CompressionService(algorithm="none")
        data = {"key": "value"}

        # Should not compress regardless of size
        assert not service.should_compress(data)

        # Compress returns original data
        result = service.compress(data)
        assert result.compression_ratio == 1.0

    def test_compression_ratio_calculation(self):
        """Test compression ratio is calculated correctly."""
        service = CompressionService()
        data = {"key": "x" * 1000}

        result = service.compress(data)
        expected_ratio = result.compressed_size / result.original_size
        assert result.compression_ratio == expected_ratio
        assert result.compression_ratio < 1.0  # Should be compressed

    def test_size_reduction_percent(self):
        """Test size reduction percentage calculation."""
        service = CompressionService()
        data = {"key": "x" * 1000}

        result = service.compress(data)
        assert result.size_reduction_percent > 0
        assert result.size_reduction_percent < 100
