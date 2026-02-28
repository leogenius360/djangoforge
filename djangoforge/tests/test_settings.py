"""
Tests for Forge settings validation.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from djangoforge.settings import ForgeSettings, forge_settings


class TestForgeSettings:
    def test_defaults(self):
        s = ForgeSettings()
        assert s.CORRELATION_ID_GENERATE is True
        assert s.EVENTS_ENABLED is True
        assert s.API_VERSION == "v1"

    def test_override(self):
        with override_settings(FORGE={"API_VERSION": "v2"}):
            s = ForgeSettings()
            assert s.API_VERSION == "v2"

    def test_unknown_setting_raises_on_access(self):
        s = ForgeSettings()
        with pytest.raises(AttributeError, match="Unknown FORGE setting"):
            s.TOTALLY_BOGUS  # noqa: B018

    def test_validate_rejects_unknown_keys(self):
        with override_settings(FORGE={"DOES_NOT_EXIST": True}):
            s = ForgeSettings()
            with pytest.raises(ImproperlyConfigured, match="Unknown FORGE setting"):
                s.validate()

    def test_as_dict(self):
        d = forge_settings.as_dict()
        assert "EVENTS_ENABLED" in d
        assert "CORRELATION_ID_HEADER" in d
