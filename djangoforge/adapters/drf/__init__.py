"""
DRF adapter — Forge-aware base classes for Django REST Framework.

Provides :class:`ForgeAPIView`, :class:`ForgeViewSet`, :class:`ForgeSerializer`,
a ``ProblemDetail`` exception handler, and auth integration that consumes
:class:`~djangoforge.api.policies.AuthPolicy`.
"""

from djangoforge.adapters.drf.authentication import ForgeAuthentication
from djangoforge.adapters.drf.exception_handler import forge_exception_handler
from djangoforge.adapters.drf.serializers import ForgeSerializer
from djangoforge.adapters.drf.views import ForgeAPIView, ForgeViewSet

__all__ = [
    "ForgeAPIView",
    "ForgeAuthentication",
    "ForgeViewSet",
    "ForgeSerializer",
    "forge_exception_handler",
]
