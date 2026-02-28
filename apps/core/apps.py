"""
Core app configuration.

The core app provides foundation-layer abstractions and utilities for the entire project.
It contains no domain logic and serves as a shared platform for all other apps.

Key components
--------------
- Base models, managers, and querysets with enterprise-safe behaviors
- Context variables for actor tracking (ASGI-safe)
- Health check and monitoring utilities
- Security helpers (token generation, fingerprinting)
- Reusable typing utilities for Django patterns

Dependencies
------------
None - this is the foundation layer.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration for the core app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"
