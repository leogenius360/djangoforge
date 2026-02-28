"""
Tests for audit registry.
"""

from django.db import models

from apps.auditing.registry import AuditModelConfig, AuditRegistry


class DummyModel(models.Model):
    """Dummy model for testing."""

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "auditing"

    def __str__(self):
        return self.name


class TestAuditConfig:
    """Test suite for AuditModelConfig."""

    def test_model_label(self):
        """Test model_label property."""
        config = AuditModelConfig(model_class=DummyModel)
        assert config.model_label == "auditing.dummymodel"

    def test_should_track_field_with_empty_track_fields(self):
        """Test that empty track_fields tracks all except excluded."""
        config = AuditModelConfig(
            model_class=DummyModel,
            track_fields=set(),
            exclude_fields={"password"},
        )

        assert config.should_track_field("name")
        assert not config.should_track_field("password")

    def test_should_track_field_with_explicit_track_fields(self):
        """Test explicit track_fields."""
        config = AuditModelConfig(
            model_class=DummyModel,
            track_fields={"name", "email"},
            exclude_fields=set(),
        )

        assert config.should_track_field("name")
        assert config.should_track_field("email")
        assert not config.should_track_field("password")

    def test_exclude_takes_precedence(self):
        """Test that exclude_fields takes precedence over track_fields."""
        config = AuditModelConfig(
            model_class=DummyModel,
            track_fields={"name", "password"},
            exclude_fields={"password"},
        )

        assert config.should_track_field("name")
        assert not config.should_track_field("password")


class TestAuditRegistry:
    """Test suite for AuditRegistry."""

    def test_register_model(self):
        """Test registering a model."""
        registry = AuditRegistry()
        registry.register(DummyModel)

        assert registry.is_registered(DummyModel)
        assert len(registry) == 1

    def test_register_model_with_config(self):
        """Test registering model with custom config."""
        registry = AuditRegistry()
        registry.register(
            DummyModel,
            enabled=True,
            track_fields={"name"},
            exclude_fields={"password"},
        )

        config = registry.get_config(DummyModel)
        assert config is not None
        assert config.enabled
        assert config.track_fields == {"name"}
        assert config.exclude_fields == {"password"}

    def test_register_already_registered_updates_config(self):
        """Test that re-registering updates config."""
        registry = AuditRegistry()
        registry.register(DummyModel, enabled=True)

        # Re-register with different settings
        registry.register(DummyModel, enabled=False)

        config = registry.get_config(DummyModel)
        assert not config.enabled

    def test_register_does_not_override_enabled_when_unspecified(self):
        """enabled should not be reset to True when register() is called without enabled."""
        registry = AuditRegistry()
        registry.register(DummyModel, enabled=False)

        # Update another field, but do not pass enabled.
        registry.register(DummyModel, track_fields={"name"})

        config = registry.get_config(DummyModel)
        assert config is not None
        assert config.enabled is False
        assert config.track_fields == {"name"}

    def test_unregister_model(self):
        """Test unregistering a model."""
        registry = AuditRegistry()
        registry.register(DummyModel)
        assert registry.is_registered(DummyModel)

        registry.unregister(DummyModel)
        assert not registry.is_registered(DummyModel)

    def test_is_enabled(self):
        """Test is_enabled check."""
        registry = AuditRegistry()
        registry.register(DummyModel, enabled=True)

        assert registry.is_enabled(DummyModel)

    def test_is_enabled_false(self):
        """Test is_enabled returns False for disabled model."""
        registry = AuditRegistry()
        registry.register(DummyModel, enabled=False)

        assert not registry.is_enabled(DummyModel)

    def test_is_enabled_not_registered(self):
        """Test is_enabled returns False for unregistered model."""
        registry = AuditRegistry()
        assert not registry.is_enabled(DummyModel)

    def test_get_all_registered_models(self):
        """Test getting all registered models."""
        registry = AuditRegistry()
        registry.register(DummyModel)

        models = registry.get_all_registered_models()
        assert DummyModel in models

    def test_get_enabled_models(self):
        """Test getting only enabled models."""
        registry = AuditRegistry()
        registry.register(DummyModel, enabled=True)

        enabled = registry.get_enabled_models()
        assert DummyModel in enabled

    def test_get_model_labels(self):
        """Test getting model labels."""
        registry = AuditRegistry()
        registry.register(DummyModel)

        labels = registry.get_model_labels()
        assert "auditing.dummymodel" in labels

    def test_should_audit_model(self):
        """Test should_audit_model logic."""
        registry = AuditRegistry()
        registry.register(DummyModel, enabled=True)

        assert registry.should_audit_model(DummyModel)

    def test_should_audit_model_disabled(self):
        """Test should_audit_model returns False for disabled."""
        registry = AuditRegistry()
        registry.register(DummyModel, enabled=False)

        assert not registry.should_audit_model(DummyModel)

    def test_should_audit_model_not_registered(self):
        """Test should_audit_model returns False for unregistered."""
        registry = AuditRegistry()
        assert not registry.should_audit_model(DummyModel)

    def test_clear_registry(self):
        """Test clearing the registry."""
        registry = AuditRegistry()
        registry.register(DummyModel)
        assert len(registry) == 1

        registry.clear()
        assert len(registry) == 0

    def test_contains_dunder_method(self):
        """Test __contains__ magic method."""
        registry = AuditRegistry()
        registry.register(DummyModel)

        assert DummyModel in registry

    def test_repr(self):
        """Test __repr__ method."""
        registry = AuditRegistry()
        registry.register(DummyModel)

        repr_str = repr(registry)
        assert "AuditRegistry" in repr_str
        assert "1 models registered" in repr_str
