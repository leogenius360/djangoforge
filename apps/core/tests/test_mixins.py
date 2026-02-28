"""
Tests for core model mixins.

Validates save/delete behaviors, optimistic locking, lifecycle transitions,
and actor tracking.
"""

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import connection, models
from django.utils import timezone

from apps.core.context import get_system_actor, set_current_actor
from apps.core.exceptions import LifecycleStateError, OptimisticLockError
from apps.core.models import EnterpriseModel

User = get_user_model()


@pytest.fixture
def test_lifecycle_model(transactional_db):
    """Create a test model with full lifecycle support."""

    class TestLifecycleModel(EnterpriseModel):
        name = models.CharField(max_length=100)
        version = models.IntegerField(default=1)

        class Meta:
            app_label = "core"

    model_name = TestLifecycleModel._meta.model_name

    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(TestLifecycleModel)

    try:
        yield TestLifecycleModel
    finally:
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(TestLifecycleModel)
        django_apps.all_models[TestLifecycleModel._meta.app_label].pop(model_name, None)


@pytest.fixture
def principal(transactional_db):
    """Create a test user with principal."""
    user = User.objects.create_user("core-mixin-user", "TestPass123!", email="test@example.com")
    return user


@pytest.mark.django_db
class TestModelOperationsMixin:
    """Tests for ModelOperationsMixin save/delete behaviors."""

    def test_save_bumps_version(self, test_lifecycle_model):
        """Test that save() increments version field."""
        instance = test_lifecycle_model.objects.create(name="test", version=1)
        original_version = instance.version

        instance.name = "updated"
        instance.save()

        assert instance.version == original_version + 1

    def test_optimistic_lock_conflict_raises(self, test_lifecycle_model):
        """Test that concurrent modification raises OptimisticLockError."""
        instance = test_lifecycle_model.objects.create(name="test", version=1)

        # Simulate concurrent modification
        test_lifecycle_model.objects.filter(pk=instance.pk).update(version=2, name="concurrent")

        # This should raise OptimisticLockError
        instance.name = "my update"
        with pytest.raises(OptimisticLockError):
            instance.save()

    def test_soft_delete_sets_deleted_at(self, test_lifecycle_model):
        """Test that delete() performs soft delete."""
        instance = test_lifecycle_model.objects.create(name="test")
        assert instance.deleted_at is None

        count, details = instance.delete()

        assert count == 1
        instance.refresh_from_db()
        assert instance.deleted_at is not None
        assert instance.is_deleted

    def test_soft_delete_bumps_version(self, test_lifecycle_model):
        """Test that soft delete increments version for consistency."""
        instance = test_lifecycle_model.objects.create(name="test", version=1)
        original_version = instance.version

        instance.delete()

        instance.refresh_from_db()
        assert instance.version == original_version + 1

    def test_hard_delete_removes_row(self, test_lifecycle_model):
        """Test that hard_delete() physically removes the row."""
        instance = test_lifecycle_model.objects.create(name="test")
        pk = instance.pk

        instance.hard_delete()

        assert not test_lifecycle_model.objects.with_deleted().filter(pk=pk).exists()

    def test_actor_tracked_on_create(self, test_lifecycle_model, principal):
        """Test that created_by is set from context on create."""
        with set_current_actor(principal):
            instance = test_lifecycle_model.objects.create(name="test")

        assert instance.created_by == principal
        assert instance.updated_by == principal

    def test_actor_tracked_on_update(self, test_lifecycle_model, principal):
        """Test that updated_by is set from context on update."""
        # Create without actor context first
        instance = test_lifecycle_model.objects.create(name="test")
        original_created_by = instance.created_by  # Will be None

        # Now update with actor context
        with set_current_actor(principal):
            instance.name = "updated"
            instance.save()

        assert instance.created_by == original_created_by  # Should not change (still None)
        assert instance.updated_by == principal

    def test_save_update_fields_list_is_supported(self, test_lifecycle_model):
        """Django allows any iterable for update_fields; mixin must handle lists."""
        instance = test_lifecycle_model.objects.create(name="test", version=1)
        original_version = instance.version

        instance.name = "updated"
        instance.save(update_fields=["name"])  # list (not set)

        instance.refresh_from_db()
        assert instance.name == "updated"
        assert instance.version == original_version + 1

    def test_enforce_actor_raises_when_unresolvable(self, test_lifecycle_model, settings):
        """When enabled, actor stamping must not silently be missing."""
        settings.CORE_ENFORCE_ACTOR = True
        settings.CORE_SYSTEM_PRINCIPAL_ID = None

        instance = test_lifecycle_model(name="test")
        # Explicitly clear actor context to test enforcement
        with set_current_actor(None), pytest.raises(ValueError, match=r"actor \(Principal\) is required"):
            instance.save()

    def test_enforce_actor_uses_system_actor_by_default(self, test_lifecycle_model, settings):
        """When enabled, automated flows must explicitly set a system actor context."""
        settings.CORE_ENFORCE_ACTOR = True

        system_actor = get_system_actor()
        assert system_actor is not None

        with set_current_actor(system_actor):
            instance = test_lifecycle_model.objects.create(name="test")
        assert instance.created_by == system_actor
        assert instance.updated_by == system_actor


@pytest.mark.django_db
class TestLifecycleMixin:
    """Tests for LifecycleMixin state transitions."""

    def test_lifecycle_transition_valid(self, test_lifecycle_model, principal):
        """Test that valid transitions succeed."""
        instance = test_lifecycle_model.objects.create(name="test")

        # ACTIVE -> DISABLED should work
        instance.disable(actor=principal, reason="Test disable")

        assert instance.is_disabled
        assert instance.disabled_at is not None
        assert instance.disabled_by == principal
        assert instance.disabled_reason == "Test disable"

    def test_lifecycle_transition_invalid_raises(self, test_lifecycle_model, principal):
        """Test that disable, lock, and suspend are independent and can all co-exist."""
        instance = test_lifecycle_model.objects.create(name="test")
        instance.disable(actor=principal, reason="User disabled")
        instance.lock(actor=principal, reason="Security lock")
        instance.suspend(actor=principal, reason="Admin suspend")

        instance.refresh_from_db()
        assert instance.is_disabled
        assert instance.is_locked
        assert instance.is_suspended

    def test_lifecycle_state_validation(self, test_lifecycle_model):
        """Test that invalid lock field combinations raise LifecycleStateError."""
        instance = test_lifecycle_model.objects.create(name="test")

        # Set locked_at without locked_until (invalid pair)
        instance.locked_at = timezone.now()
        instance.locked_until = None

        with pytest.raises(LifecycleStateError):
            instance.save()

    def test_lock_sets_fields(self, test_lifecycle_model, principal):
        """Test that lock() sets all required lock fields."""
        instance = test_lifecycle_model.objects.create(name="test")

        instance.lock(actor=principal, reason="Security lock")

        assert instance.is_locked
        assert instance.locked_at is not None
        assert instance.locked_until is not None
        assert instance.locked_until > instance.locked_at
        assert instance.locked_by == principal
        assert instance.locked_reason == "Security lock"

    def test_unlock_clears_fields(self, test_lifecycle_model, principal):
        """Test that unlock() clears lock fields. is_active is unaffected (lock never changed it)."""
        instance = test_lifecycle_model.objects.create(name="test")
        instance.lock(actor=principal)

        instance.unlock(actor=principal, reason="Unlocked")

        assert not instance.is_locked
        assert instance.locked_at is None
        assert instance.locked_until is None
        assert instance.locked_by is None
        assert instance.locked_reason == ""

    def test_unlock_honors_explicit_actor_over_context(self, test_lifecycle_model, principal, db):
        """unlock(actor=...) should stamp updated_by from the explicit actor, not thread-local."""
        user2 = User.objects.create_user("core-mixin-user2", "TestPass123!", email="test2@example.com")
        principal2 = user2

        instance = test_lifecycle_model.objects.create(name="test", version=1)
        instance.lock(actor=principal)

        with set_current_actor(principal):
            instance.unlock(actor=principal2)

        instance.refresh_from_db()
        assert instance.updated_by == principal2

    def test_disable_convenience_method(self, test_lifecycle_model, principal):
        """Test disable() convenience method."""
        instance = test_lifecycle_model.objects.create(name="test")

        instance.disable(actor=principal, reason="Admin action")

        assert instance.is_disabled
        assert instance.disabled_at is not None
        assert instance.disabled_by == principal

    def test_enable_convenience_method(self, test_lifecycle_model, principal):
        """Test enable() convenience method."""
        # Create in ACTIVE state first, then disable it
        instance = test_lifecycle_model.objects.create(name="test")
        instance.disable(actor=principal, reason="Test")

        # Now enable it
        instance.enable(actor=principal)

        assert instance.is_active
        assert instance.disabled_at is None

    def test_suspend_and_unsuspend(self, test_lifecycle_model, principal):
        """Test suspend() and unsuspend() convenience methods."""
        instance = test_lifecycle_model.objects.create(name="test")
        assert instance.is_active

        # Suspend - should set is_active False
        instance.suspend(actor=principal, reason="Policy violation")
        assert instance.is_suspended
        assert instance.suspended_at is not None
        assert not instance.is_active

        # Unsuspend - should restore is_active when no other restriction remains
        instance.unsuspend(actor=principal)
        assert not instance.is_suspended
        assert instance.suspended_at is None
        assert instance.is_active

    def test_unsuspend_honors_explicit_actor_over_context(self, test_lifecycle_model, principal):
        """unsuspend(actor=...) should stamp updated_by from the explicit actor, not thread-local."""
        user2 = User.objects.create_user("core-mixin-user3", "TestPass123!", email="test3@example.com")
        principal2 = user2

        instance = test_lifecycle_model.objects.create(name="test")
        instance.suspend(actor=principal)

        with set_current_actor(principal):
            instance.unsuspend(actor=principal2)

        instance.refresh_from_db()
        assert instance.updated_by == principal2


@pytest.mark.django_db
class TestLiftRestriction:
    """Tests for scoped restriction lifting (unlock/unsuspend/enable)."""

    def test_unlock_preserves_disabled_restriction(self, test_lifecycle_model, principal):
        """unlock() should not restore is_active when disabled restriction still exists."""
        instance = test_lifecycle_model.objects.create(name="test")
        instance.lock(actor=principal)
        assert instance.is_locked
        assert not instance.is_active

        # Simulate a disabled restriction at the field level
        instance.disabled_at = timezone.now()
        instance.disabled_by = principal
        instance.save_without_version_bump(update_fields={"disabled_at", "disabled_by"})

        instance.unlock(actor=principal)

        instance.refresh_from_db()
        assert instance.locked_at is None
        assert instance.locked_until is None
        assert instance.locked_by is None
        assert instance.is_disabled
        assert not instance.is_active

    def test_unlock_clears_lock_fields(self, test_lifecycle_model, principal):
        """lock() sets is_active False; unlock() restores it when no other restriction remains."""
        instance = test_lifecycle_model.objects.create(name="test")
        assert instance.is_active

        instance.lock(actor=principal)
        assert instance.is_locked
        assert not instance.is_active

        instance.unlock(actor=principal)

        instance.refresh_from_db()
        assert not instance.is_locked
        assert instance.locked_at is None
        assert instance.is_active

    def test_unsuspend_preserves_disabled_restriction(self, test_lifecycle_model, principal):
        """unsuspend() should not restore is_active when disabled restriction still exists."""
        instance = test_lifecycle_model.objects.create(name="test")
        instance.suspend(actor=principal, reason="Policy")
        assert instance.is_suspended
        assert not instance.is_active

        instance.disabled_at = timezone.now()
        instance.disabled_by = principal
        instance.save_without_version_bump(update_fields={"disabled_at", "disabled_by"})

        instance.unsuspend(actor=principal)

        instance.refresh_from_db()
        assert instance.suspended_at is None
        assert instance.suspended_by is None
        assert instance.is_disabled
        assert not instance.is_active

    def test_enable_preserves_suspended_restriction(self, test_lifecycle_model, principal):
        """enable() should not restore is_active when suspended restriction still exists."""
        instance = test_lifecycle_model.objects.create(name="test")
        instance.disable(actor=principal, reason="Admin")
        assert instance.is_disabled
        assert not instance.is_active

        instance.suspended_at = timezone.now()
        instance.suspended_by = principal
        instance.save_without_version_bump(update_fields={"suspended_at", "suspended_by"})

        instance.enable(actor=principal)

        instance.refresh_from_db()
        assert instance.disabled_at is None
        assert instance.disabled_by is None
        assert instance.is_suspended
        assert not instance.is_active

    def test_unlock_on_non_locked_is_noop(self, test_lifecycle_model, principal):
        """unlock() on a non-locked instance is a silent no-op (idempotent)."""
        instance = test_lifecycle_model.objects.create(name="test")
        assert not instance.is_locked
        assert instance.is_active

        instance.unlock(actor=principal)  # should not raise

        assert not instance.is_locked
        assert instance.is_active

    def test_unsuspend_on_non_suspended_is_noop(self, test_lifecycle_model, principal):
        """unsuspend() on a non-suspended instance is a silent no-op (idempotent)."""
        instance = test_lifecycle_model.objects.create(name="test")
        assert not instance.is_suspended
        assert instance.is_active

        instance.unsuspend(actor=principal)  # should not raise

        assert not instance.is_suspended
        assert instance.is_active

    def test_enable_on_non_disabled_is_noop(self, test_lifecycle_model, principal):
        """enable() on a non-disabled instance is a silent no-op (idempotent)."""
        instance = test_lifecycle_model.objects.create(name="test")
        assert not instance.is_disabled
        assert instance.is_active

        instance.enable(actor=principal)  # should not raise

        assert not instance.is_disabled
        assert instance.is_active


@pytest.mark.django_db
class TestDeleteActorStamping:
    """Tests for deleted_by stamping during soft delete."""

    def test_delete_stamps_deleted_by(self, test_lifecycle_model, principal):
        """delete() should stamp deleted_by when actor is in context."""
        instance = test_lifecycle_model.objects.create(name="test")

        with set_current_actor(principal):
            instance.delete()

        instance.refresh_from_db()
        assert instance.deleted_at is not None
        assert instance.deleted_by == principal

    def test_soft_delete_stamps_deleted_by(self, test_lifecycle_model, principal):
        """SoftDeleteMixin.soft_delete() should stamp deleted_by."""
        instance = test_lifecycle_model.objects.create(name="test")

        instance.soft_delete(actor=principal)

        instance.refresh_from_db()
        assert instance.deleted_at is not None
        assert instance.deleted_by == principal

    def test_soft_delete_accepts_update_fields(self, test_lifecycle_model, principal):
        """soft_delete() should persist caller-provided update_fields alongside managed fields."""
        instance = test_lifecycle_model.objects.create(name="test")
        instance.name = "updated-before-delete"

        instance.soft_delete(actor=principal, update_fields={"name"})

        instance.refresh_from_db()
        assert instance.deleted_at is not None
        assert instance.name == "updated-before-delete"
