"""
Forge-aware DRF serializer base class.
"""

from __future__ import annotations

from rest_framework import serializers


class ForgeSerializer(serializers.Serializer):
    """Base serializer that includes a ``correlation_id`` in error output."""
