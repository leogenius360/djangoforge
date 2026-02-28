"""Session enums and constants.

This module is part of the public `apps.sessions.models` surface.
Provides DeviceType enum for device classification.
"""

from django.db import models


class DeviceType(models.TextChoices):
    """Device type classification."""

    DESKTOP = "desktop", "Desktop"
    MOBILE = "mobile", "Mobile"
    TABLET = "tablet", "Tablet"
    WEB = "web", "Web Browser"
    CLI = "cli", "Command Line Interface"
    API = "api", "API Client"
    IOT = "iot", "IoT Device"
    UNKNOWN = "unknown", "Unknown"
