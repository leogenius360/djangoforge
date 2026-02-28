"""API tests for audit log endpoints."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client as APIClient

from apps.auditing.models import Event, EventType

User = get_user_model()


@pytest.mark.django_db
class TestAuditApiAccess:
    """Test audit API access control and responses."""

    def setup_method(self):
        self.client = APIClient()

    def _create_staff_user(self):
        user = User.objects.create_user(
            username=f"staffuser-{uuid.uuid4().hex[:8]}",
            email=f"staff-{uuid.uuid4().hex[:8]}@example.com",
            password="SecurePass123!",
        )
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        return user

    def _unique_email(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"

    def _create_audit_entries(self, actor, target):
        content_type = ContentType.objects.get_for_model(target.__class__)

        entry1 = Event.objects.create(
            content_type=content_type,
            object_id=str(target.pk),
            event_type=EventType.CREATE,
            actor=actor,
            snapshot={"username": target.username},
            version=1,
        )
        entry2 = Event.objects.create(
            content_type=content_type,
            object_id=str(target.pk),
            event_type=EventType.UPDATE,
            actor=actor,
            parent=entry1,
            snapshot={"username": target.username, "email": target.email},
            version=2,
        )

        return entry1, entry2

    def test_requires_authentication(self):
        """Unauthenticated requests should be denied."""
        response = self.client.get("/api/audit/events/")
        assert response.status_code in (401, 403)

    def test_requires_staff(self, user_factory):
        """Non-staff users should be denied access to audit API."""
        user = user_factory()
        self.client.force_login(user)

        response = self.client.get("/api/audit/events/")

        assert response.status_code == 403

    def test_list_events(self, user_factory):
        """Staff users can list audit events."""
        staff_user = self._create_staff_user()
        target = user_factory(username="targetuser", email=self._unique_email("target"))
        self._create_audit_entries(staff_user, target)

        self.client.force_login(staff_user)
        response = self.client.get("/api/audit/events/")

        assert response.status_code == 200

    def test_list_events_filter_event_type(self, user_factory):
        """Staff users can filter events by event_type."""
        staff_user = self._create_staff_user()
        target = user_factory(email=self._unique_email("ft"))
        self._create_audit_entries(staff_user, target)

        self.client.force_login(staff_user)
        response = self.client.get("/api/audit/events/", {"event_type": "create"})

        assert response.status_code == 200
        data = response.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        for event in results:
            assert event["event_type"] == "create"

    def test_get_event_detail(self, user_factory):
        """Staff users can retrieve audit event details."""
        staff_user = self._create_staff_user()
        target = user_factory(username="detailuser", email=self._unique_email("detail"))
        entry, _ = self._create_audit_entries(staff_user, target)

        self.client.force_login(staff_user)
        response = self.client.get(f"/api/audit/events/{entry.id}/")

        assert response.status_code == 200
        assert response.json()["id"] == str(entry.id)
        assert response.json()["object_id"] == str(target.pk)

    def test_history_endpoint(self, user_factory):
        """History endpoint returns timeline for object ordered by version."""
        staff_user = self._create_staff_user()
        target = user_factory(username="historyuser", email=self._unique_email("history"))
        self._create_audit_entries(staff_user, target)

        content_type = ContentType.objects.get_for_model(target.__class__)
        content_type_str = f"{content_type.app_label}.{content_type.model}"

        self.client.force_login(staff_user)
        response = self.client.get(
            "/api/audit/history/",
            {"content_type": content_type_str, "object_id": str(target.pk)},
        )

        assert response.status_code == 200
        assert len(response.json()) >= 2

    def test_history_endpoint_missing_params(self):
        """History endpoint returns 400 when required params are missing."""
        staff_user = self._create_staff_user()
        self.client.force_login(staff_user)

        response = self.client.get("/api/audit/history/")
        assert response.status_code == 400

    def test_history_endpoint_requires_staff(self, user_factory):
        """Non-staff users cannot access history endpoint."""
        user = user_factory()
        self.client.force_login(user)

        response = self.client.get(
            "/api/audit/history/",
            {"content_type": "auth.user", "object_id": "1"},
        )
        assert response.status_code == 403

    def test_version_endpoint(self, user_factory):
        """Version endpoint reconstructs state at a specific version."""
        staff_user = self._create_staff_user()
        target_email = self._unique_email("replay")
        target = user_factory(username="replayuser", email=target_email)
        self._create_audit_entries(staff_user, target)

        content_type = ContentType.objects.get_for_model(target.__class__)
        content_type_str = f"{content_type.app_label}.{content_type.model}"

        self.client.force_login(staff_user)
        response = self.client.get(
            "/api/audit/version/",
            {
                "content_type": content_type_str,
                "object_id": str(target.pk),
                "version": 2,
            },
        )

        assert response.status_code == 200
        assert response.json()["version"] == 2
        assert "state" in response.json()

    def test_version_endpoint_invalid_version(self):
        """Version endpoint returns 400 for non-integer version."""
        staff_user = self._create_staff_user()
        self.client.force_login(staff_user)

        response = self.client.get(
            "/api/audit/version/",
            {
                "content_type": "auth.user",
                "object_id": "1",
                "version": "notanumber",
            },
        )
        assert response.status_code == 400

    def test_version_endpoint_not_found(self):
        """Version endpoint returns 404 when version does not exist."""
        staff_user = self._create_staff_user()
        self.client.force_login(staff_user)

        # Use the actual User content type (ensures it exists in the DB)
        ct = ContentType.objects.get_for_model(User)
        content_type_str = f"{ct.app_label}.{ct.model}"

        response = self.client.get(
            "/api/audit/version/",
            {
                "content_type": content_type_str,
                "object_id": str(uuid.uuid4()),
                "version": 999,
            },
        )
        assert response.status_code == 404
