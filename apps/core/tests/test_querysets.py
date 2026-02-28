"""
Tests for core QuerySet functionality.

Validates soft delete, bulk operations, version bumping, and related behaviors.
"""

import pytest
from django.apps import apps as django_apps
from django.db import connection, models
from django.utils import timezone

from apps.core.models import SoftDeleteModel


@pytest.fixture
def test_model(transactional_db):
    """Create a test model with soft delete support."""

    class TestSoftDeleteModel(SoftDeleteModel):
        name = models.CharField(max_length=100)
        version = models.IntegerField(default=1)

        class Meta:
            app_label = "core"

    model_name = TestSoftDeleteModel._meta.model_name

    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(TestSoftDeleteModel)

    try:
        yield TestSoftDeleteModel
    finally:
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(TestSoftDeleteModel)
        django_apps.all_models[TestSoftDeleteModel._meta.app_label].pop(model_name, None)


@pytest.mark.django_db
class TestSoftDeleteQuerySet:
    """Tests for soft delete queryset behaviors."""

    def test_active_filters_deleted_at_null(self, test_model):
        """Test that active() returns only non-deleted instances."""
        # Create test instances
        active = test_model.objects.create(name="active")
        deleted = test_model.objects.create(name="deleted", deleted_at=timezone.now())

        # Test active() filter
        active_qs = test_model.objects.all()
        assert active_qs.count() == 1
        assert active in active_qs
        assert deleted not in active_qs

    def test_deleted_filters_deleted_at_set(self, test_model):
        """Test that deleted() returns only soft-deleted instances."""
        active = test_model.objects.create(name="active")
        deleted = test_model.objects.create(name="deleted", deleted_at=timezone.now())

        deleted_qs = test_model.objects.deleted()
        assert deleted_qs.count() == 1
        assert deleted in deleted_qs
        assert active not in deleted_qs

    def test_with_deleted_returns_all(self, test_model):
        """Test that with_deleted() returns both active and deleted instances."""
        active = test_model.objects.create(name="active")
        deleted = test_model.objects.create(name="deleted", deleted_at=timezone.now())

        all_qs = test_model.objects.with_deleted()
        assert all_qs.count() == 2
        assert active in all_qs
        assert deleted in all_qs

    def test_soft_delete_sets_timestamp(self, test_model):
        """Test that soft_delete() sets deleted_at timestamp."""
        instance = test_model.objects.create(name="test")
        assert instance.deleted_at is None

        # Soft delete via queryset
        count, details = test_model.objects.filter(pk=instance.pk).soft_delete()

        assert count == 1
        instance.refresh_from_db()
        assert instance.deleted_at is not None

    def test_restore_clears_deleted_at(self, test_model):
        """Test that restore() clears deleted_at."""
        instance = test_model.objects.create(name="test", deleted_at=timezone.now())

        # Restore via queryset
        count = test_model.objects.with_deleted().filter(pk=instance.pk).restore()

        assert count == 1
        instance.refresh_from_db()
        assert instance.deleted_at is None

    def test_hard_delete_removes_row(self, test_model):
        """Test that hard_delete() physically removes the row."""
        instance = test_model.objects.create(name="test")
        pk = instance.pk

        # Hard delete via queryset
        test_model.objects.filter(pk=pk).hard_delete()

        assert not test_model.objects.with_deleted().filter(pk=pk).exists()


@pytest.mark.django_db
class TestBulkConsistencyQuerySet:
    """Tests for bulk operation consistency (updated_at, version)."""

    def test_bulk_update_bumps_version(self, test_model):
        """Test that update() increments version field."""
        instance = test_model.objects.create(name="test", version=1)
        original_version = instance.version

        # Bulk update
        test_model.objects.filter(pk=instance.pk).update(name="updated")

        instance.refresh_from_db()
        assert instance.name == "updated"
        assert instance.version == original_version + 1

    def test_update_sets_updated_at(self, test_model):
        """Test that update() sets updated_at timestamp."""
        instance = test_model.objects.create(name="test")
        original_updated_at = instance.updated_at

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.01)

        # Bulk update
        test_model.objects.filter(pk=instance.pk).update(name="updated")

        instance.refresh_from_db()
        assert instance.updated_at > original_updated_at

    def test_update_without_version_skips_bump(self, test_model):
        """Test that update_without_version() doesn't increment version."""
        instance = test_model.objects.create(name="test", version=1)
        original_version = instance.version

        # Bulk update without version bump
        test_model.objects.filter(pk=instance.pk).update_without_version(name="updated")

        instance.refresh_from_db()
        assert instance.name == "updated"
        assert instance.version == original_version

    def test_bulk_update_instances(self, test_model):
        """Test bulk_update() maintains version and updated_at."""
        instances = [test_model.objects.create(name=f"test{i}", version=1) for i in range(3)]

        for i, instance in enumerate(instances):
            instance.name = f"updated{i}"

        test_model.objects.bulk_update(instances, ["name"])

        for instance in instances:
            instance.refresh_from_db()
            assert "updated" in instance.name
            assert instance.version == 2  # Should be bumped
