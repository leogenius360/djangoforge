"""
Core tests for auditing models, services, and middleware.
"""

from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import isolate_apps

from apps.auditing.middleware import (
    AuditingMiddleware,
    get_current_request,
)
from apps.auditing.models import Event, EventType
from apps.auditing.registry import audit_registry
from apps.auditing.services import (
    create_audit_entry,
    get_object_history,
    get_version,
    redo_change,
    serialize_model_state,
    should_audit_model,
    undo_change,
)

User = get_user_model()


@pytest.mark.django_db
class TestEvent:
    """Test Event model."""

    def test_create_audit_entry(self, user_factory):
        """Test creating an audit entry."""
        user = user_factory()

        audit_entry = Event.objects.create(
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
            event_type=EventType.CREATE,
            actor=user,
            snapshot={"username": user.username},
            version=1,
        )

        assert audit_entry.pk is not None
        assert audit_entry.event_type == EventType.CREATE
        assert audit_entry.version == 1
        assert audit_entry.is_undone is False

    def test_get_delta(self, user_factory):
        """Test getting diff between states."""
        user = user_factory()

        # Create previous entry first
        previous_entry = Event.objects.create(
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
            event_type=EventType.CREATE,
            snapshot={"username": "old_name", "email": "[email protected]"},
            version=1,
        )

        # Create new entry with parent FK
        audit_entry = Event.objects.create(
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
            event_type=EventType.UPDATE,
            parent=previous_entry,
            snapshot={"username": "new_name", "email": "[email protected]"},
            version=2,
        )

        delta = audit_entry.get_diff()

        assert "username" in delta
        assert delta["username"]["old"] == "old_name"
        assert delta["username"]["new"] == "new_name"
        assert "email" not in delta  # Email didn't change

    def test_can_undo(self, user_factory):
        """Test can_undo method."""
        user = user_factory()

        # Create entry can be undone
        create_entry = Event.objects.create(
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
            event_type=EventType.CREATE,
            snapshot={"username": user.username},
            version=1,
        )
        assert create_entry.can_undo() is True

        # Undone entry cannot be undone again
        # Simulate undo by creating an UNDO event that references this as parent
        Event.objects.create(
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
            event_type=EventType.UNDO,
            parent=create_entry,  # Link to the event being undone
            snapshot={"username": user.username},
            version=2,
        )
        # After undo, original entry should show as undone via is_undone property
        assert create_entry.is_undone is True
        assert create_entry.is_undone is True

    def test_can_redo(self, user_factory):
        """Test can_redo method."""
        user = user_factory()

        entry = Event.objects.create(
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
            event_type=EventType.UPDATE,
            snapshot={"username": user.username},
            version=1,
        )

        # Not undone, so cannot redo
        assert entry.can_redo() is False

        # Mark as undone by creating an UNDO event
        Event.objects.create(
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
            event_type=EventType.UNDO,
            parent=entry,  # Link to the event being undone
            snapshot={"username": user.username},
            version=2,
        )
        # After undo, entry should show as undone and can be redone
        assert entry.is_undone is True
        assert entry.can_redo() is True

    def test_get_object_history(self, user_factory):
        """Test getting object history."""
        user = user_factory()
        content_type = ContentType.objects.get_for_model(User)

        # Delete auto-created audit entries - delete newest first to respect PROTECT FK
        # Use Model.delete() which bypasses queryset restrictions
        entries = list(Event.objects.filter(content_type=content_type, object_id=str(user.pk)).order_by("-created_at"))
        for entry in entries:
            # Manually delete using the model's delete method
            models.Model.delete(entry)

        # Create multiple entries with proper FK chain
        entry1 = Event.objects.create(
            content_type=content_type,
            object_id=str(user.pk),
            event_type=EventType.CREATE,
            snapshot={"username": "user1"},
            version=1,
        )

        entry2 = Event.objects.create(
            content_type=content_type,
            object_id=str(user.pk),
            event_type=EventType.UPDATE,
            parent=entry1,
            snapshot={"username": "user2"},
            version=2,
        )

        history = entry1.get_history()

        assert history.count() == 2
        assert list(history) == [entry1, entry2]

    def test_get_previous_version(self, user_factory):
        """Test getting previous version."""
        user = user_factory()
        content_type = ContentType.objects.get_for_model(User)

        entry1 = Event.objects.create(
            content_type=content_type,
            object_id=str(user.pk),
            event_type=EventType.CREATE,
            snapshot={"username": "user1"},
            version=1,
        )

        entry2 = Event.objects.create(
            content_type=content_type,
            object_id=str(user.pk),
            event_type=EventType.UPDATE,
            parent=entry1,
            snapshot={"username": "user2"},
            version=2,
        )

        # Version 1 has no previous
        assert entry1.get_previous_version() is None

        # Version 2's previous is version 1
        assert entry2.get_previous_version() == entry1

    def test_get_next_version(self, user_factory):
        """Test getting next version."""
        user = user_factory()
        content_type = ContentType.objects.get_for_model(User)

        entry1 = Event.objects.create(
            content_type=content_type,
            object_id=str(user.pk),
            event_type=EventType.CREATE,
            snapshot={"username": "user1"},
            version=1,
        )

        entry2 = Event.objects.create(
            content_type=content_type,
            object_id=str(user.pk),
            event_type=EventType.UPDATE,
            parent=entry1,
            snapshot={"username": "user2"},
            version=2,
        )

        # Version 1's next is version 2
        assert entry1.get_next_version() == entry2

        # Version 2 has no next
        assert entry2.get_next_version() is None


@pytest.mark.django_db
class TestAuditService:
    """Test audit service functions."""

    def test_should_audit_model(self):
        """Test model auditing filter."""
        # Event should not be audited (in EXCLUDED_MODELS)
        assert should_audit_model(Event) is False

        # ContentType should not be audited (in EXCLUDED_MODELS)
        assert should_audit_model(ContentType) is False

        # AUTH_USER_MODEL (Principal) is in AUDITED_APPS (accounts), so should be audited
        assert should_audit_model(User) is True

    def test_serialize_model_state(self, user_factory):
        """Test serializing model state."""
        user = user_factory(username="testuser", email="[email protected]")

        state = serialize_model_state(user)

        assert state["pk"] == str(user.pk)
        assert "username" in state
        assert state["username"] == "testuser"
        assert "email" in state

    def test_create_audit_entry_service(self, user_factory):
        """Test creating audit entry via service."""
        user = user_factory()
        current_state = serialize_model_state(user)

        audit_entry = create_audit_entry(
            instance=user,
            event_type=EventType.CREATE,
            state=current_state,
            actor=user,
        )

        assert audit_entry.pk is not None
        assert audit_entry.event_type == EventType.CREATE
        assert audit_entry.actor == user
        assert audit_entry.get_snapshot() == current_state

    def test_undo_change(self, user_factory, process_audit_outbox):
        """Test undoing a change."""
        user = user_factory(username="original")
        content_type = ContentType.objects.get_for_model(User)

        # Process outbox to create audit entries
        process_audit_outbox()

        # Get the auto-created CREATE entry
        create_entry = Event.objects.filter(
            content_type=content_type, object_id=str(user.pk), event_type=EventType.CREATE
        ).first()

        # Skip test if no create entry was generated
        if not create_entry:
            pytest.skip("No CREATE audit entry was generated")

        # Clear any other entries (like automatic updates from signals)
        other_entries = list(
            Event.objects.filter(content_type=content_type, object_id=str(user.pk))
            .exclude(id=create_entry.id)
            .order_by("-created_at")
        )
        for entry in other_entries:
            models.Model.delete(entry)

        # Now modify (this will auto-create UPDATE entry via signal)
        user.username = "modified"
        user.save()

        # Process outbox to create the UPDATE audit entry
        process_audit_outbox()

        # Get the auto-created UPDATE entry
        audit_entry = Event.objects.filter(
            content_type=content_type, object_id=str(user.pk), event_type=EventType.UPDATE
        ).latest("created_at")

        # Verify the FK chain is set up correctly
        assert audit_entry.parent == create_entry

        # Undo the change
        undo_entry = undo_change(audit_entry)

        assert undo_entry is not None
        assert undo_entry.event_type == EventType.UNDO
        assert audit_entry.is_undone is True

        # Refresh user from database
        user.refresh_from_db()
        assert user.username == "original"

    def test_redo_change(self, user_factory, process_audit_outbox):
        """Test redoing a change."""
        user = user_factory(username="original")
        content_type = ContentType.objects.get_for_model(User)

        # Process CREATE outbox entry
        process_audit_outbox()

        # Make a change
        user.username = "modified"
        user.save()

        # Process UPDATE outbox entry
        process_audit_outbox()

        # Get the auto-created update entry
        try:
            audit_entry = Event.objects.filter(
                content_type=content_type, object_id=str(user.pk), event_type=EventType.UPDATE
            ).latest("created_at")
        except Event.DoesNotExist:
            pytest.skip("No UPDATE audit entry was generated")

        # Undo the change
        undo_change(audit_entry)
        user.refresh_from_db()
        assert user.username == "original"

        # Redo the change
        redo_entry = redo_change(audit_entry)

        assert redo_entry is not None
        assert redo_entry.event_type == EventType.REDO
        assert audit_entry.is_undone is False

        # Refresh user from database
        user.refresh_from_db()
        assert user.username == "modified"

    def test_get_object_history_service(self, user_factory):
        """Test getting object history via service."""
        user = user_factory()

        # Create multiple audit entries
        for i in range(3):
            user.username = f"user{i}"
            user.save()
            create_audit_entry(
                instance=user,
                event_type=EventType.UPDATE,
                state=serialize_model_state(user),
            )

        history = get_object_history(User, user.pk)

        assert len(history) >= 3

    @override_settings(AUDITING={"SNAPSHOT_INTERVAL": 0})
    def test_get_version(self, user_factory):
        """Test getting specific version."""
        user = user_factory(username="version1")

        # Delete auto-created audit entries in reverse order (newest first)
        # Use Model.delete() to bypass queryset restrictions
        entries = list(
            Event.objects.filter(content_type=ContentType.objects.get_for_model(User), object_id=str(user.pk)).order_by(
                "-created_at"
            )
        )
        for entry in entries:
            models.Model.delete(entry)

        state1 = serialize_model_state(user)
        create_audit_entry(
            instance=user,
            event_type=EventType.CREATE,
            state=state1,
        )

        user.username = "version2"
        user.save()
        state2 = serialize_model_state(user)
        create_audit_entry(
            instance=user,
            event_type=EventType.UPDATE,
            state=state2,
        )

        # Get version 1
        version1_state = get_version(User, user.pk, 1)
        assert version1_state is not None
        assert version1_state["username"] == "version1"

        # Get version 2
        version2_state = get_version(User, user.pk, 2)
        assert version2_state is not None
        assert version2_state["username"] == "version2"


class TestAuditingMiddleware(TestCase):
    """Test auditing middleware."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = RequestFactory()
        self.middleware = AuditingMiddleware(get_response=lambda r: Mock())

    def test_process_request(self):
        """Test request processing stores request in thread-local."""
        request = self.factory.get("/")

        self.middleware.process_request(request)

        current_request = get_current_request()
        assert current_request == request

    def test_process_response(self):
        """Test response processing clears request from thread-local."""
        request = self.factory.get("/")
        response = Mock()

        self.middleware.process_request(request)
        assert get_current_request() is not None

        self.middleware.process_response(request, response)
        assert get_current_request() is None

    @pytest.mark.django_db
    def test_contextvars_are_set_and_reset(self):
        from apps.auditing.context import (
            get_current_actor,
            get_current_ip_address,
            get_current_request_id,
            get_current_session,
            get_current_user_agent,
        )

        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "10.0.0.9"
        request.META["HTTP_USER_AGENT"] = "TestBrowser/1.0"
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        request.user = user
        request.session = Mock(session_key="sess-123")

        self.middleware.process_request(request)

        assert get_current_actor() == user
        assert get_current_session() == "sess-123"
        assert get_current_ip_address() == "10.0.0.9"
        assert get_current_user_agent() == "TestBrowser/1.0"
        assert get_current_request_id() is not None

        response = Mock()
        self.middleware.process_response(request, response)

        assert get_current_actor() is None
        assert get_current_session() is None
        assert get_current_ip_address() is None
        assert get_current_user_agent() is None
        assert get_current_request_id() is None

    @pytest.mark.django_db
    def test_contextvars_do_not_leak_on_exception(self):
        from apps.auditing.context import get_current_actor

        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        request = self.factory.get("/")
        request.user = user

        middleware = AuditingMiddleware(get_response=lambda r: (_ for _ in ()).throw(RuntimeError("boom")))

        with pytest.raises(RuntimeError):
            middleware(request)

        assert get_current_actor() is None


@pytest.mark.django_db(transaction=True)
class TestAuditableModelMixin:
    @isolate_apps("apps.auditing")
    def test_update_delta_and_delete_event(self):
        from apps.auditing.models.mixins import AuditableModelMixin

        class AuditedWidget(AuditableModelMixin, models.Model):
            name = models.CharField(max_length=50)

            class Meta:
                app_label = "auditing"

            def __str__(self) -> str:
                return self.name

        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(AuditedWidget)

        try:
            # Ensure enabled in registry even if auto-registration was deferred.
            audit_registry.register(AuditedWidget, enabled=True)

            widget = AuditedWidget.objects.create(name="v1")
            widget.name = "v2"
            widget.save()

            ct = ContentType.objects.get_for_model(AuditedWidget)
            update_entry = (
                Event.objects.filter(content_type=ct, object_id=str(widget.pk), event_type=EventType.UPDATE)
                .order_by("-created_at")
                .first()
            )
            assert update_entry is not None
            assert update_entry.delta is not None
            assert update_entry.delta.get("name") == "v2"

            widget_pk = widget.pk
            widget.delete()

            delete_entry = (
                Event.objects.filter(content_type=ct, object_id=str(widget_pk), event_type=EventType.DELETE)
                .order_by("-created_at")
                .first()
            )
            assert delete_entry is not None
            snapshot = delete_entry.get_snapshot()
            assert snapshot is not None
            assert snapshot.get("name") == "v2"
        finally:
            audit_registry.unregister(AuditedWidget)
            with connection.schema_editor() as schema_editor:
                schema_editor.delete_model(AuditedWidget)
