"""
Tests for Forge checks framework integration.
"""

from django.core.checks import run_checks
from django.test import override_settings

import djangoforge.checks  # noqa: F401 — ensure checks are registered


class TestForgeChecks:
    def test_warns_when_correlation_middleware_missing(self):
        with override_settings(MIDDLEWARE=[]):
            errors = run_checks(tags=["forge"])
            ids = [e.id for e in errors]
            assert "forge.W001" in ids

    def test_warns_when_security_middleware_missing(self):
        with override_settings(MIDDLEWARE=[], FORGE={"SECURITY_HEADERS_ENABLED": True}):
            errors = run_checks(tags=["forge"])
            ids = [e.id for e in errors]
            assert "forge.W002" in ids
