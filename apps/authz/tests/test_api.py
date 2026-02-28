"""API tests for the authz app."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from apps.accounts.models import Principal
from apps.authz.enums import PermissionAction, PolicyEffect
from apps.authz.models import RoleAssignment


@pytest.fixture
def api_client():
    return APIClient()


# ---------------------------------------------------------------
# Authentication required
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestAuthRequired:
    """All endpoints require authentication."""

    def test_permissions_list(self, api_client):
        resp = api_client.get("/api/authz/permissions/")
        assert resp.status_code in (401, 403)

    def test_roles_list(self, api_client):
        resp = api_client.get("/api/authz/roles/")
        assert resp.status_code in (401, 403)

    def test_assignments_list(self, api_client):
        resp = api_client.get("/api/authz/assignments/")
        assert resp.status_code in (401, 403)

    def test_policies_list(self, api_client):
        resp = api_client.get("/api/authz/policies/")
        assert resp.status_code in (401, 403)

    def test_check(self, api_client):
        resp = api_client.post("/api/authz/check/")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------
# Permission endpoints
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestPermissionAPI:
    def test_list_permissions(self, api_client, user_principal, read_perm):
        api_client.force_authenticate(user=user_principal)
        resp = api_client.get("/api/authz/permissions/")
        assert resp.status_code == 200
        assert len(resp.data["results"]) >= 1

    def test_create_permission_staff_only(self, api_client, user_principal, staff_principal, principal_ct):
        # Non-staff cannot create
        api_client.force_authenticate(user=user_principal)
        resp = api_client.post(
            "/api/authz/permissions/",
            {
                "name": "Delete",
                "content_type": principal_ct.pk,
                "action": PermissionAction.DELETE,
            },
            format="json",
        )
        assert resp.status_code == 403

        # Staff can create
        api_client.force_authenticate(user=staff_principal)
        resp = api_client.post(
            "/api/authz/permissions/",
            {
                "name": "Delete Principal",
                "content_type": principal_ct.pk,
                "action": PermissionAction.DELETE,
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["codename"] == "accounts.principal.delete"


# ---------------------------------------------------------------
# Role endpoints
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestRoleAPI:
    def test_list_roles(self, api_client, user_principal, viewer_role):
        api_client.force_authenticate(user=user_principal)
        resp = api_client.get("/api/authz/roles/")
        assert resp.status_code == 200

    def test_create_role_staff_only(self, api_client, user_principal, staff_principal, principal_ct):
        api_client.force_authenticate(user=user_principal)
        resp = api_client.post(
            "/api/authz/roles/",
            {"codename": "new.role", "name": "New Role"},
            format="json",
        )
        assert resp.status_code == 403

        api_client.force_authenticate(user=staff_principal)
        resp = api_client.post(
            "/api/authz/roles/",
            {
                "codename": "new.role",
                "name": "New Role",
                "content_type": principal_ct.pk,
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_detail_includes_permissions_and_ancestors(self, api_client, staff_principal, editor_role):
        api_client.force_authenticate(user=staff_principal)
        resp = api_client.get(f"/api/authz/roles/{editor_role.pk}/")
        assert resp.status_code == 200
        assert "permissions" in resp.data
        assert "ancestors" in resp.data
        assert len(resp.data["ancestors"]) == 1  # viewer is parent

    def test_delete_role(self, api_client, staff_principal, viewer_role):
        api_client.force_authenticate(user=staff_principal)
        resp = api_client.delete(f"/api/authz/roles/{viewer_role.pk}/")
        assert resp.status_code == 204


# ---------------------------------------------------------------
# Role assignment endpoints
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestAssignmentAPI:
    def test_create_assignment(self, api_client, staff_principal, user_principal, viewer_role):
        api_client.force_authenticate(user=staff_principal)
        ct = ContentType.objects.get_for_model(user_principal)
        resp = api_client.post(
            "/api/authz/assignments/",
            {
                "principal": str(user_principal.pk),
                "role": str(viewer_role.pk),
                "resource_type": f"{ct.app_label}.{ct.model}",
                "resource_id": str(user_principal.pk),
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_list_assignments(self, api_client, user_principal):
        api_client.force_authenticate(user=user_principal)
        resp = api_client.get("/api/authz/assignments/")
        assert resp.status_code == 200

    def test_delete_assignment(self, api_client, staff_principal, user_principal, viewer_role):
        ct = ContentType.objects.get_for_model(user_principal)
        assignment = RoleAssignment.objects.create(
            principal=user_principal,
            role=viewer_role,
            content_type=ct,
            object_id=user_principal.pk,
        )
        api_client.force_authenticate(user=staff_principal)
        resp = api_client.delete(f"/api/authz/assignments/{assignment.pk}/")
        assert resp.status_code == 204


# ---------------------------------------------------------------
# Policy endpoints
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestPolicyAPI:
    def test_list_policies_staff_only(self, api_client, user_principal, staff_principal):
        api_client.force_authenticate(user=user_principal)
        resp = api_client.get("/api/authz/policies/")
        assert resp.status_code == 403

        api_client.force_authenticate(user=staff_principal)
        resp = api_client.get("/api/authz/policies/")
        assert resp.status_code == 200

    def test_create_policy(self, api_client, staff_principal, principal_ct):
        api_client.force_authenticate(user=staff_principal)
        resp = api_client.post(
            "/api/authz/policies/",
            {
                "codename": "api.test.policy",
                "name": "API Test Policy",
                "effect": PolicyEffect.ALLOW,
                "condition": 'principal.kind == "user"',
                "content_type": principal_ct.pk,
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["codename"] == "api.test.policy"

    def test_create_policy_invalid_condition(self, api_client, staff_principal, principal_ct):
        api_client.force_authenticate(user=staff_principal)
        resp = api_client.post(
            "/api/authz/policies/",
            {
                "codename": "bad.cond",
                "name": "Bad",
                "effect": PolicyEffect.ALLOW,
                "condition": "== bad",
                "content_type": principal_ct.pk,
            },
            format="json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------
# Check endpoint
# ---------------------------------------------------------------


@pytest.mark.django_db
class TestCheckAPI:
    def test_check_denied(self, api_client, user_principal, staff_principal):
        api_client.force_authenticate(user=user_principal)
        ct = ContentType.objects.get_for_model(staff_principal)
        resp = api_client.post(
            "/api/authz/check/",
            {
                "action": "read",
                "resource_type": f"{ct.app_label}.{ct.model}",
                "resource_id": str(staff_principal.pk),
            },
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["allowed"] is False

    def test_check_allowed_via_rbac(self, api_client, user_principal, viewer_role, staff_principal):
        ct = ContentType.objects.get_for_model(staff_principal)
        RoleAssignment.objects.create(
            principal=user_principal,
            role=viewer_role,
            content_type=ct,
            object_id=staff_principal.pk,
        )

        api_client.force_authenticate(user=user_principal)
        resp = api_client.post(
            "/api/authz/check/",
            {
                "action": "read",
                "resource_type": f"{ct.app_label}.{ct.model}",
                "resource_id": str(staff_principal.pk),
            },
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["allowed"] is True

    def test_check_resource_not_found(self, api_client, user_principal):
        import uuid

        api_client.force_authenticate(user=user_principal)
        ct = ContentType.objects.get_for_model(Principal)
        resp = api_client.post(
            "/api/authz/check/",
            {
                "action": "read",
                "resource_type": f"{ct.app_label}.{ct.model}",
                "resource_id": str(uuid.uuid4()),
            },
            format="json",
        )
        assert resp.status_code == 404
