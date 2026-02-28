"""
Forge-aware DRF views.
"""

from __future__ import annotations

from rest_framework.generics import GenericAPIView
from rest_framework.viewsets import ModelViewSet


class ForgeAPIView(GenericAPIView):
    """Base API view with Forge defaults.

    Subclass this instead of ``GenericAPIView`` to get the Forge exception
    handler and authentication wired automatically.
    """


class ForgeViewSet(ModelViewSet):
    """Base viewset with Forge defaults."""
