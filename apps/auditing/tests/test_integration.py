"""
Integration tests for complete audit system.

Tests end-to-end workflows: signal-driven event creation, undo/redo,
multi-backend dispatch, snapshot replay, and immutability enforcement.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Principal
from apps.auditing.backends.coordinator import MultiBackendCoordinator
from apps.auditing.backends.file import FileAuditBackend
from apps.auditing.models import Event, EventType
from apps.auditing.services import (
    create_audit_entry,
    get_version,
    redo_change,
    serialize_model_state,
    undo_change,
)


class TestEndToEndAuditWorkflow(TestCase):
    """Test complete audit workflow from creation to replay."""

    def setUp(self):
        self.user = Principal.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.test_obj = Principal.objects.create_user(
            username="auditeduser",
            email="audited@example.com",
            password="password123",
        )

    def test_create_audit_entry_persists(self):
        """Creating an audit entry stores a record in the database."""
        state = serialize_model_state(self.test_obj)
        entry = create_audit_entry(
            instance=self.test_obj,
            event_type=EventType.UPDATE,
            state=state,
            actor=self.user,
            comment="Basic audit test",
        )

        self.assertIsNotNone(entry)
        self.assertIsNotNone(entry.pk)
        self.assertEqual(entry.event_type, EventType.UPDATE)
        self.assertIsNotNone(entry.checksum)
        self.assertNotEqual(entry.checksum, "")

    def test_integrity_verification_workflow(self):
        """All events for an object pass integrity verification."""
        for i in range(3):
            create_audit_entry(
                instance=self.test_obj,
                event_type=EventType.UPDATE,
                state={"username": f"user{i}", "version": i},
                actor=self.user,
                comment=f"Update {i}",
            )

        entries = Event.objects.filter(object_id=str(self.test_obj.id)).order_by("created_at")

        for entry in entries:
            self.assertTrue(
                entry.verify_integrity(),
                f"Entry {entry.id} failed integrity check",
            )

    def test_multi_backend_write(self):
        """Writing to file backend succeeds alongside DB."""
        temp_dir = tempfile.mkdtemp()
        try:
            file_backend = FileAuditBackend(base_path=temp_dir, compress=False, rotate_daily=False)
            coordinator = MultiBackendCoordinator(strict_mode=False, backends=[file_backend])
            content_type = ContentType.objects.get_for_model(Principal)

            result = coordinator.write(
                content_type_id=content_type.id,
                object_id=str(self.test_obj.id),
                event_type="update",
                current_state={"username": "updated"},
                changes={"username": {"old": "auditeduser", "new": "updated"}},
                user_id=str(self.user.id),
                session_id=None,
                comment="Multi-backend test",
                object_version=1,
            )

            self.assertTrue(result["success"])
            log_file = Path(temp_dir) / "audit.json"
            self.assertTrue(log_file.exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_version_replay(self):
        """get_version() returns the snapshot at the requested version."""
        state1 = {"username": "user_v1", "email": "user1@example.com"}
        entry1 = create_audit_entry(
            instance=self.test_obj,
            event_type=EventType.CREATE,
            state=state1,
            actor=self.user,
            comment="Version A",
        )

        state2 = {"username": "user_v2", "email": "user2@example.com"}
        entry2 = create_audit_entry(
            instance=self.test_obj,
            event_type=EventType.UPDATE,
            state=state2,
            pre_state=state1,
            actor=self.user,
            comment="Version B",
        )

        retrieved_v1 = get_version(Principal, self.test_obj.id, entry1.version)
        self.assertIsNotNone(retrieved_v1)
        self.assertEqual(retrieved_v1.get("username"), "user_v1")

        retrieved_v2 = get_version(Principal, self.test_obj.id, entry2.version)
        self.assertIsNotNone(retrieved_v2)
        self.assertEqual(retrieved_v2.get("username"), "user_v2")

    @override_settings(AUDITING={"SNAPSHOT_INTERVAL": 0})
    def test_compression_snapshot_roundtrip(self):
        """set_snapshot / get_snapshot round-trip works without compression."""
        state = serialize_model_state(self.test_obj)
        entry = create_audit_entry(
            instance=self.test_obj,
            event_type=EventType.UPDATE,
            state=state,
            actor=self.user,
            comment="Compression test",
        )

        restored = entry.get_snapshot()
        self.assertIsNotNone(restored)
        self.assertIsInstance(restored, dict)

    def test_undo_redo_workflow(self):
        """Undo creates an UNDO event; redo reverses it."""
        # Create initial state
        create_entry = create_audit_entry(
            instance=self.test_obj,
            event_type=EventType.CREATE,
            state={"username": "auditeduser"},
            actor=self.user,
            comment="Initial state",
        )

        # Create update
        update_entry = create_audit_entry(
            instance=self.test_obj,
            event_type=EventType.UPDATE,
            state={"username": "updated"},
            pre_state={"username": "auditeduser"},
            actor=self.user,
            comment="Update state",
        )

        self.assertEqual(update_entry.parent, create_entry)

        # Undo the update
        undo_entry = undo_change(update_entry)
        self.assertIsNotNone(undo_entry)
        self.assertEqual(undo_entry.event_type, EventType.UNDO)

        update_entry.refresh_from_db()
        self.assertTrue(update_entry.is_undone)

        # Redo the update
        redo_entry = redo_change(update_entry)
        self.assertIsNotNone(redo_entry)
        self.assertEqual(redo_entry.event_type, EventType.REDO)


class TestConcurrentAuditing(TestCase):
    """Test version sequencing under rapid sequential writes."""

    def setUp(self):
        self.user1 = Principal.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="pass123",
        )
        self.user2 = Principal.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="pass123",
        )

    def test_sequential_version_increments(self):
        """Rapidly created entries get distinct, sequential version numbers."""
        entries = []
        for i in range(5):
            entry = create_audit_entry(
                instance=self.user1,
                event_type=EventType.UPDATE,
                state={"version": i},
                actor=self.user2,
                comment=f"Update {i}",
            )
            entries.append(entry)

        versions = [e.version for e in entries]
        # All versions must be unique and ascending
        self.assertEqual(len(set(versions)), len(versions))
        self.assertEqual(versions, sorted(versions))


class TestSecurityFeatures(TestCase):
    """Test security-related integrity features."""

    def setUp(self):
        self.user = Principal.objects.create_user(
            username="sectest",
            email="security@example.com",
            password="secure123",
        )

    def test_checksum_is_stored(self):
        """Audit entries have a non-empty checksum."""
        entry = create_audit_entry(
            instance=self.user,
            event_type=EventType.UPDATE,
            state={"username": "testuser"},
            actor=self.user,
            comment="Checksum test",
        )
        self.assertIsNotNone(entry.checksum)
        self.assertNotEqual(entry.checksum, "")

    def test_integrity_verification_passes(self):
        """verify_integrity() returns True for fresh events."""
        entry = create_audit_entry(
            instance=self.user,
            event_type=EventType.UPDATE,
            state={"username": "original"},
            actor=self.user,
            comment="Test entry",
        )
        self.assertTrue(entry.verify_integrity())

    def test_immutability_rejects_snapshot_modification(self):
        """Modifying snapshot after creation raises an immutability error."""
        from apps.auditing.exceptions import ImmutabilityError

        entry = create_audit_entry(
            instance=self.user,
            event_type=EventType.UPDATE,
            state={"username": "original"},
            actor=self.user,
            comment="Test entry",
        )

        entry.snapshot = {"username": "tampered"}
        with self.assertRaises((ImmutabilityError, ValueError)):
            entry.save(update_fields=["snapshot"])


class TestEventImmutableUpdates(TestCase):
    """Ensure sensitive Event fields are immutable across all update paths."""

    def setUp(self):
        self.user = Principal.objects.create_user(
            "integ_immutable",
            "secure123",
            email="integ_immutable@example.com",
        )

    def _create_entry(self, comment: str = "test"):
        return create_audit_entry(
            instance=self.user,
            event_type=EventType.UPDATE,
            state={"username": "original"},
            actor=self.user,
            comment=comment,
        )

    def test_mutable_comment_update_succeeds(self):
        """comment is mutable after creation."""
        entry = self._create_entry("Publish flag update")
        entry.comment = "Updated comment"
        entry.save(update_fields=["comment"])
        entry.refresh_from_db()
        self.assertEqual(entry.comment, "Updated comment")

    def test_save_rejects_sensitive_field_update(self):
        """Updating snapshot via save(update_fields=["snapshot"]) raises error."""
        from apps.auditing.exceptions import ImmutabilityError

        entry = self._create_entry("Attempt to tamper")
        entry.snapshot = {"username": "tampered"}
        with self.assertRaises((ImmutabilityError, ValueError)):
            entry.save(update_fields=["snapshot"])

    def test_queryset_update_rejects_immutable_fields(self):
        """Queryset .update() on immutable fields raises error."""
        from apps.auditing.exceptions import ImmutabilityError

        entry = self._create_entry("Bulk update guard")
        with self.assertRaises((ImmutabilityError, ValueError)):
            type(entry).objects.filter(pk=entry.pk).update(snapshot={"username": "tampered"})

    def test_queryset_update_allows_deleted_at(self):
        """Queryset .update(deleted_at=...) is allowed."""
        entry = self._create_entry("Soft-delete test")
        updated = type(entry).objects.filter(pk=entry.pk).update(deleted_at=timezone.now())
        self.assertEqual(updated, 1)

    def test_bulk_update_rejects_sensitive_fields(self):
        """bulk_update on immutable fields raises error."""
        from apps.auditing.exceptions import ImmutabilityError

        entry = self._create_entry("bulk_update guard")
        entry.snapshot = {"username": "tampered"}
        with self.assertRaises((ImmutabilityError, ValueError)):
            type(entry).objects.bulk_update([entry], ["snapshot"])

    def test_full_save_without_update_fields_is_rejected(self):
        """Calling save() without update_fields is forbidden."""
        from apps.auditing.exceptions import ImmutabilityError

        entry = self._create_entry("Full save attempt")
        with self.assertRaises((ImmutabilityError, ValueError)):
            entry.save()  # no update_fields → rejected
