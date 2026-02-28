"""
Ninja adapter — Forge-aware utilities for Django Ninja.

Provides :func:`forge_router`, a ``ProblemDetail`` exception handler, and
auth backend that consumes :class:`~djangoforge.api.policies.AuthPolicy`.

.. note::

   Django Ninja is an *optional* dependency. Import this module only when
   ``ninja`` is installed.
"""

from djangoforge.adapters.ninja.auth import ForgeNinjaAuth
from djangoforge.adapters.ninja.exception_handler import forge_ninja_exception_handler
from djangoforge.adapters.ninja.router import forge_router

__all__ = [
    "ForgeNinjaAuth",
    "forge_ninja_exception_handler",
    "forge_router",
]
