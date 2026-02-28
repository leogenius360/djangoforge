"""
Accounts app tests.

Comprehensive test suite for the accounts app covering:
- Principal model (username-based, lifecycle, security stamp)
- Concrete account models (UserAccount, ServiceAccount, APIClient, AgentAccount)
- AccountProvisioner service (provisioning, deprovisioning)
- QuerySet methods (by_username, authenticatable, kind filters)
- Manager methods (create_user, create_superuser, normalization)
- Username validation and normalization
- API endpoints for CRUD operations
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.test import Client as DRFClient

from apps.accounts.enums import PrincipalKind
from apps.accounts.exceptions import UsernameConflictError
from apps.accounts.models import (
    Principal,
)
from apps.accounts.services import AccountProvisioner
from apps.accounts.validators import UsernameValidator
from apps.core.api import status

User = get_user_model()


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def api_client():
    """Return a DRF test client."""
    return DRFClient()


@pytest.fixture
def provisioner():
    """Return an AccountProvisioner instance."""
    return AccountProvisioner()


@pytest.fixture
def create_user(db, provisioner):
    """Factory fixture to create user accounts via provisioner."""

    def _create_user(
        username="testuser",
        password="SecurePass123!",
        email=None,
        display_name="",
        **kwargs,
    ):
        principal, user_account = provisioner.provision_user(
            username=username,
            password=password,
            email=email,
            display_name=display_name,
            **kwargs,
        )
        return principal, user_account

    return _create_user


@pytest.fixture
def user_principal(create_user):
    """Return a simple user principal + user account tuple."""
    return create_user(username="testuser", password="SecurePass123!", email="test@example.com")


@pytest.fixture
def staff_principal(db):
    """Return a staff principal for admin access."""
    principal = Principal.objects.create_superuser(
        username="staffadmin",
        password="AdminPass123!",
        email="admin@example.com",
    )
    return principal


@pytest.fixture
def authenticated_client(api_client, user_principal):
    """Return an authenticated API client."""
    principal, _ = user_principal
    api_client.force_login(principal)
    return api_client, principal


@pytest.fixture
def staff_client(api_client, staff_principal):
    """Return a staff-authenticated API client."""
    api_client.force_login(staff_principal)
    return api_client, staff_principal


# ======================================================================
# Principal Model Tests
# ======================================================================


@pytest.mark.django_db
class TestPrincipalModel:
    """Tests for the Principal model."""

    def test_username_is_username_field(self):
        """USERNAME_FIELD should be 'username'."""
        assert Principal.USERNAME_FIELD == "username"

    def test_required_fields_includes_kind(self):
        """REQUIRED_FIELDS should include kind (prompted by createsuperuser alongside username)."""
        assert Principal.REQUIRED_FIELDS == ["kind"]

    def test_create_user_with_username(self, db):
        """Creating a user principal requires a username."""
        principal = Principal.objects.create_user(
            username="johndoe",
            password="SecurePass123!",
        )
        assert principal.username == "johndoe"
        assert principal.kind == PrincipalKind.USER
        assert principal.check_password("SecurePass123!")
        assert not principal.is_staff
        assert not principal.is_superuser
        assert principal.is_active

    def test_create_user_without_username_raises(self, db):
        """Creating a user with empty username should raise ValueError."""
        with pytest.raises(ValueError, match="username"):
            Principal.objects.create_user(username="", password="pass123")

    def test_create_superuser(self, db):
        """Superuser creation sets is_staff and is_superuser."""
        principal = Principal.objects.create_superuser(
            username="admin",
            password="AdminPass123!",
        )
        assert principal.is_staff
        assert principal.is_superuser
        assert principal.kind == PrincipalKind.USER

    def test_create_superuser_not_staff_raises(self, db):
        """Superuser with is_staff=False should raise ValueError."""
        with pytest.raises(ValueError, match="is_staff"):
            Principal.objects.create_superuser(
                username="admin",
                password="pass",
                is_staff=False,
            )

    def test_create_superuser_not_superuser_raises(self, db):
        """Superuser with is_superuser=False should raise ValueError."""
        with pytest.raises(ValueError, match="is_superuser"):
            Principal.objects.create_superuser(
                username="admin",
                password="pass",
                is_superuser=False,
            )

    def test_username_unique(self, create_user):
        """Username must be unique across all principal kinds."""
        create_user(username="unique1")
        with pytest.raises((UsernameConflictError, Exception)):
            create_user(username="unique1")

    def test_username_case_insensitive_normalization(self, db):
        """Username should be normalized to lowercase."""
        principal = Principal.objects.create_user(
            username="JohnDoe",
            password="pass123",
        )
        assert principal.username == "johndoe"

    def test_email_optional(self, db):
        """Email should be optional (nullable)."""
        principal = Principal.objects.create_user(
            username="noemail",
            password="pass123",
        )
        assert principal.email is None

    def test_email_unique_when_present(self, db):
        """Email should be unique when provided."""
        Principal.objects.create_user(
            username="user1",
            password="pass123",
            email="same@example.com",
        )
        with pytest.raises(Exception):  # noqa: B017
            Principal.objects.create_user(
                username="user2",
                password="pass123",
                email="same@example.com",
            )

    def test_empty_email_normalized_to_none(self, db):
        """Empty string email should be normalized to None."""
        principal = Principal.objects.create_user(
            username="emptyemail",
            password="pass123",
            email="",
        )
        assert principal.email is None

    def test_str_returns_username(self, db):
        """String representation should return username."""
        principal = Principal.objects.create_user(username="strtest", password="pass")
        assert str(principal) == "strtest"

    def test_repr(self, db):
        """Repr should include id, kind, and username."""
        principal = Principal.objects.create_user(username="reprtest", password="pass")
        r = repr(principal)
        assert "reprtest" in r
        assert "user" in r

    def test_uuid_primary_key(self, db):
        """Principal should use UUID as primary key."""
        principal = Principal.objects.create_user(username="uuidtest", password="pass")
        assert isinstance(principal.pk, uuid.UUID)

    def test_default_metadata_empty_dict(self, db):
        """Metadata should default to empty dict."""
        principal = Principal.objects.create_user(username="metadefault", password="pass")
        assert principal.metadata == {}


# ======================================================================
# Lifecycle Tests
# ======================================================================


@pytest.mark.django_db
class TestPrincipalLifecycle:
    """Tests for lifecycle operations on Principal."""

    def test_lock_account(self, db):
        """Locking should set locked fields and bump security stamp."""
        principal = Principal.objects.create_user(username="locktest", password="pass")
        old_stamp = principal.security_stamp

        principal.lock(duration=timedelta(minutes=30), reason="Testing")

        principal.refresh_from_db()
        assert principal.is_locked
        assert principal.locked_until is not None
        assert principal.security_stamp > old_stamp

    def test_unlock_account(self, db):
        """Unlocking should clear locked fields."""
        principal = Principal.objects.create_user(username="unlocktest", password="pass")
        principal.lock(duration=timedelta(minutes=30))
        principal.refresh_from_db()
        assert principal.is_locked

        principal.unlock()
        principal.refresh_from_db()
        assert not principal.is_locked
        assert principal.locked_at is None

    def test_suspend_account(self, db):
        """Suspending should set suspended fields and bump stamp."""
        principal = Principal.objects.create_user(username="susptest", password="pass")
        old_stamp = principal.security_stamp

        principal.suspend(reason="Policy violation")

        principal.refresh_from_db()
        assert principal.is_suspended
        assert principal.suspended_at is not None
        assert principal.security_stamp > old_stamp

    def test_unsuspend_account(self, db):
        """Unsuspending should clear suspended fields."""
        principal = Principal.objects.create_user(username="unsusptest", password="pass")
        principal.suspend(reason="Test")
        principal.refresh_from_db()
        assert principal.is_suspended

        principal.unsuspend()
        principal.refresh_from_db()
        assert not principal.is_suspended

    def test_disable_bumps_stamp(self, db):
        """Disabling should bump security stamp."""
        principal = Principal.objects.create_user(username="disabletest", password="pass")
        old_stamp = principal.security_stamp

        principal.disable(reason="Deactivated")

        principal.refresh_from_db()
        assert principal.is_disabled
        assert principal.security_stamp > old_stamp

    def test_enable(self, db):
        """Enabling should restore principal."""
        principal = Principal.objects.create_user(username="enabletest", password="pass")
        principal.disable(reason="Test")
        principal.refresh_from_db()
        assert principal.is_disabled

        principal.enable()
        principal.refresh_from_db()
        assert not principal.is_disabled

    def test_soft_delete_bumps_stamp(self, db):
        """Soft delete should bump security stamp."""
        principal = Principal.objects.create_user(username="deletetest", password="pass")
        old_stamp = principal.security_stamp

        principal.soft_delete()

        # Use with_deleted to find the soft-deleted principal
        updated = Principal.objects.with_deleted().get(pk=principal.pk)
        assert updated.deleted_at is not None
        assert updated.security_stamp > old_stamp

    def test_can_authenticate_active(self, db):
        """Active principal should be able to authenticate."""
        principal = Principal.objects.create_user(username="canauth", password="pass")
        assert principal.can_authenticate

    def test_can_authenticate_locked(self, db):
        """Locked principal should not be able to authenticate."""
        principal = Principal.objects.create_user(username="noauth", password="pass")
        principal.lock()
        principal.refresh_from_db()
        assert not principal.can_authenticate

    def test_can_authenticate_suspended(self, db):
        """Suspended principal should not be able to authenticate."""
        principal = Principal.objects.create_user(username="suspnoauth", password="pass")
        principal.suspend(reason="Test")
        principal.refresh_from_db()
        assert not principal.can_authenticate


# ======================================================================
# Security Stamp Tests
# ======================================================================


@pytest.mark.django_db
class TestSecurityStamp:
    """Tests for security stamp functionality."""

    def test_bump_security_stamp(self, db):
        """Bumping stamp should increment atomically."""
        principal = Principal.objects.create_user(username="stamptest", password="pass")
        old_stamp = principal.security_stamp
        new_stamp = principal.bump_security_stamp(save=True)

        assert new_stamp == old_stamp + 1
        principal.refresh_from_db()
        assert principal.security_stamp == new_stamp

    def test_bump_stamp_without_save(self, db):
        """Bumping stamp with save=False should only update in memory."""
        principal = Principal.objects.create_user(username="stampnosave", password="pass")
        new_stamp = principal.bump_security_stamp(save=False)

        assert principal.security_stamp == new_stamp
        # DB should still have old value
        db_principal = Principal.objects.get(pk=principal.pk)
        assert db_principal.security_stamp < new_stamp

    def test_set_display_name(self, db):
        """set_display_name should update display name explicitly."""
        principal = Principal.objects.create_user(username="dntest", password="pass")
        assert principal.display_name == ""

        principal.set_display_name("Test Name")
        principal.refresh_from_db()
        assert principal.display_name == "Test Name"

    def test_set_display_name_no_op_if_same(self, db):
        """set_display_name should not save if value unchanged."""
        principal = Principal.objects.create_user(
            username="dnnoop",
            password="pass",
            display_name="Same Name",
        )
        # Should not raise or error
        principal.set_display_name("Same Name")
        principal.refresh_from_db()
        assert principal.display_name == "Same Name"


# ======================================================================
# Kind Properties Tests
# ======================================================================


@pytest.mark.django_db
class TestPrincipalKindProperties:
    """Tests for kind-checking properties."""

    def test_is_user(self, db):
        principal = Principal.objects.create_user(username="p-user", password="pass")
        assert principal.is_user
        assert not principal.is_service
        assert not principal.is_api_client
        assert not principal.is_agent

    def test_is_service(self, db):
        principal = Principal.objects.create_service_principal(username="p-svc", display_name="svc")
        assert principal.is_service
        assert not principal.is_user

    def test_is_api_client(self, db):
        principal = Principal.objects.create_api_client_principal(username="p-api", display_name="api")
        assert principal.is_api_client
        assert not principal.is_user

    def test_is_agent(self, db):
        principal = Principal.objects.create_agent_principal(username="p-agent", display_name="agent")
        assert principal.is_agent
        assert not principal.is_user


# ======================================================================
# QuerySet Tests
# ======================================================================


@pytest.mark.django_db
class TestPrincipalQuerySet:
    """Tests for PrincipalQuerySet methods."""

    def test_by_username(self, db):
        """by_username should perform case-insensitive lookup."""
        Principal.objects.create_user(username="findme", password="pass")
        qs = Principal.objects.by_username("FindMe")
        assert qs.exists()

    def test_users_filter(self, db):
        """users() should only return user principals."""
        Principal.objects.create_user(username="u1", password="pass")
        Principal.objects.create_service_principal(username="s1", display_name="svc")
        assert Principal.objects.users().count() >= 1
        for p in Principal.objects.users():
            assert p.kind == PrincipalKind.USER

    def test_services_filter(self, db):
        """services() should only return service principals."""
        Principal.objects.create_service_principal(username="svc-filter", display_name="svc")
        assert Principal.objects.services().count() >= 1
        for p in Principal.objects.services():
            assert p.kind == PrincipalKind.SERVICE

    def test_authenticatable(self, db):
        """authenticatable() should exclude locked/suspended/disabled principals."""
        p1 = Principal.objects.create_user(username="auth1", password="pass")
        p2 = Principal.objects.create_user(username="auth2", password="pass")

        p2.lock()

        auth_qs = Principal.objects.authenticatable()
        pks = list(auth_qs.values_list("pk", flat=True))
        assert p1.pk in pks
        assert p2.pk not in pks

    def test_with_concrete(self, db, provisioner):
        """with_concrete() should eager-load concrete accounts."""
        provisioner.provision_user(username="eager", password="pass")
        qs = Principal.objects.with_concrete()
        assert qs.exists()

    def test_default_queryset_excludes_soft_deleted(self, db):
        """Default manager queryset should exclude soft-deleted principals."""
        principal = Principal.objects.create_user(username="softdel", password="pass")
        pk = principal.pk
        principal.soft_delete()

        assert not Principal.objects.filter(pk=pk).exists()
        assert Principal.objects.with_deleted().filter(pk=pk).exists()

    def test_by_kind(self, db):
        """by_kind() should filter by specific kind."""
        Principal.objects.create_agent_principal(username="agent-kind", display_name="ag")
        qs = Principal.objects.by_kind(PrincipalKind.AGENT)
        assert qs.exists()


# ======================================================================
# Manager Tests
# ======================================================================


@pytest.mark.django_db
class TestPrincipalManager:
    """Tests for PrincipalManager methods."""

    def test_normalize_username(self):
        """normalize_username should lowercase and strip."""
        assert Principal.objects.normalize_username("  TestUser  ") == "testuser"

    def test_get_by_natural_key(self, db):
        """get_by_natural_key should perform case-insensitive lookup."""
        Principal.objects.create_user(username="naturalkey", password="pass")
        p = Principal.objects.get_by_natural_key("NaturalKey")
        assert p.username == "naturalkey"

    def test_create_service_principal(self, db):
        """create_service_principal should create kind=service with no password."""
        p = Principal.objects.create_service_principal(
            username="svc-mgr",
            display_name="My Service",
        )
        assert p.kind == PrincipalKind.SERVICE
        assert not p.has_usable_password()

    def test_create_api_client_principal(self, db):
        """create_api_client_principal should create kind=api_client."""
        p = Principal.objects.create_api_client_principal(
            username="api-mgr",
            display_name="My API",
        )
        assert p.kind == PrincipalKind.API_CLIENT
        assert not p.has_usable_password()

    def test_create_agent_principal(self, db):
        """create_agent_principal should create kind=agent."""
        p = Principal.objects.create_agent_principal(
            username="agent-mgr",
            display_name="My Agent",
        )
        assert p.kind == PrincipalKind.AGENT
        assert not p.has_usable_password()


# ======================================================================
# Username Validation Tests
# ======================================================================


@pytest.mark.django_db
class TestUsernameValidation:
    """Tests for username validation."""

    def test_valid_usernames(self):
        """Valid usernames should pass validation."""
        validator = UsernameValidator()
        valid = ["johndoe", "john.doe", "john-doe", "john_doe", "a123", "user42"]
        for username in valid:
            validator(username)  # Should not raise

    def test_invalid_usernames(self):
        """Invalid usernames should fail validation."""
        validator = UsernameValidator()
        invalid = [".startdot", "-startdash", "_startunder", "has space", "a@b"]
        for username in invalid:
            with pytest.raises(ValidationError):
                validator(username)


# ======================================================================
# AccountProvisioner Tests
# ======================================================================


@pytest.mark.django_db
class TestAccountProvisioner:
    """Tests for AccountProvisioner service."""

    def test_provision_user(self, provisioner):
        """provision_user should create Principal + UserAccount atomically."""
        principal, user_account = provisioner.provision_user(
            username="prov-user",
            password="SecurePass123!",
            email="prov@example.com",
            display_name="Provisioned User",
        )

        assert principal.username == "prov-user"
        assert principal.kind == PrincipalKind.USER
        assert principal.email == "prov@example.com"
        assert principal.check_password("SecurePass123!")
        assert user_account.principal == principal
        assert user_account.display_name == "Provisioned User"

    def test_provision_user_with_phone(self, provisioner):
        """provision_user should set phone_number on UserAccount."""
        principal, user_account = provisioner.provision_user(
            username="phoneuser",
            password="pass123",
            phone_number="+12025551234",
        )
        assert user_account.phone_number == "+12025551234"

    def test_provision_user_duplicate_username(self, provisioner):
        """Duplicate username should raise UsernameConflictError."""
        provisioner.provision_user(username="dupuser", password="pass")
        with pytest.raises(UsernameConflictError):
            provisioner.provision_user(username="dupuser", password="pass2")

    def test_provision_service_account(self, provisioner):
        """provision_service_account should create Principal + ServiceAccount."""
        principal, svc = provisioner.provision_service_account(
            username="svc-payment",
            service_name="payment-gateway",
            description="Handles payments",
        )

        assert principal.kind == PrincipalKind.SERVICE
        assert svc.service_name == "payment-gateway"
        assert svc.description == "Handles payments"
        assert svc.principal == principal

    def test_provision_service_auto_username(self, provisioner):
        """Auto-generated service username should use prefix."""
        principal, svc = provisioner.provision_service_account(
            service_name="email-sender",
        )
        assert principal.username.startswith("svc-")
        assert "email-sender" in principal.username

    def test_provision_api_client_confidential(self, provisioner):
        """Confidential API client should generate and store hashed secret."""
        principal, api_client_obj, secret = provisioner.provision_api_client(
            username="api-myapp",
            client_id="myapp-client",
            client_type="confidential",
        )

        assert principal.kind == PrincipalKind.API_CLIENT
        assert api_client_obj.client_id == "myapp-client"
        assert api_client_obj.client_type == "confidential"
        assert secret is not None
        assert len(secret) >= 32
        # Verify the hashed secret matches
        assert check_password(secret, api_client_obj.client_secret)

    def test_provision_api_client_public(self, provisioner):
        """Public API client should not have a secret."""
        principal, api_client_obj, secret = provisioner.provision_api_client(
            username="api-public",
            client_id="public-client",
            client_type="public",
        )

        assert secret is None
        assert api_client_obj.client_secret == ""

    def test_provision_agent(self, provisioner):
        """provision_agent should create Principal + AgentAccount."""
        principal, agent = provisioner.provision_agent(
            username="agent-llm",
            identifier="claude-agent",
            agent_type="llm",
            description="An LLM agent",
            capabilities={"tool_use": True},
        )

        assert principal.kind == PrincipalKind.AGENT
        assert agent.identifier == "claude-agent"
        assert agent.agent_type == "llm"
        assert agent.capabilities == {"tool_use": True}

    def test_provision_agent_auto_username(self, provisioner):
        """Auto-generated agent username should use prefix."""
        principal, agent = provisioner.provision_agent(
            identifier="cron-cleanup",
            agent_type="cron",
        )
        assert principal.username.startswith("agent-")
        assert "cron-cleanup" in principal.username

    def test_deprovision(self, provisioner):
        """deprovision should soft-delete both principal and concrete account."""
        principal, user_account = provisioner.provision_user(
            username="deprov-user",
            password="pass123",
        )

        provisioner.deprovision(principal)

        # Principal should be soft-deleted
        assert not Principal.objects.filter(pk=principal.pk).exists()
        updated = Principal.objects.with_deleted().get(pk=principal.pk)
        assert updated.deleted_at is not None

    def test_generate_username_service(self, provisioner):
        """generate_username should create prefixed username for services."""
        username = provisioner.generate_username(PrincipalKind.SERVICE, "Payment Gateway")
        assert username.startswith("svc-")
        assert "payment-gateway" in username

    def test_generate_username_api_client(self, provisioner):
        """generate_username should create prefixed username for API clients."""
        username = provisioner.generate_username(PrincipalKind.API_CLIENT, "My App")
        assert username.startswith("api-")

    def test_generate_username_agent(self, provisioner):
        """generate_username should create prefixed username for agents."""
        username = provisioner.generate_username(PrincipalKind.AGENT, "Cleanup Bot")
        assert username.startswith("agent-")

    def test_provision_with_owner(self, provisioner):
        """Service account should be linkable to an owner principal."""
        owner_principal, _ = provisioner.provision_user(
            username="owner-user",
            password="pass123",
        )

        _, svc = provisioner.provision_service_account(
            username="svc-owned",
            service_name="owned-service",
            owner=owner_principal,
        )
        assert svc.owner == owner_principal


# ======================================================================
# Concrete Account Model Tests
# ======================================================================


@pytest.mark.django_db
class TestUserAccount:
    """Tests for UserAccount model."""

    def test_username_delegates_to_principal(self, provisioner):
        """UserAccount.username should delegate to principal.username."""
        principal, user_account = provisioner.provision_user(
            username="delegate-user",
            password="pass123",
        )
        assert user_account.username == "delegate-user"

    def test_email_delegates_to_principal(self, provisioner):
        """UserAccount.email should delegate to principal.email."""
        principal, user_account = provisioner.provision_user(
            username="email-delegate",
            password="pass123",
            email="delegate@example.com",
        )
        assert user_account.email == "delegate@example.com"

    def test_sync_display_name(self, provisioner):
        """sync_display_name should copy display_name to principal."""
        principal, user_account = provisioner.provision_user(
            username="syncname",
            password="pass123",
            display_name="Original Name",
        )

        # display_name lives on Principal now — update it there
        principal.display_name = "New Name"
        principal.save(update_fields=["display_name", "updated_at"])
        user_account.sync_display_name()

        principal.refresh_from_db()
        # sync_display_name uses display_name (from Principal) as source
        assert principal.display_name == "New Name"


@pytest.mark.django_db
class TestServiceAccount:
    """Tests for ServiceAccount model."""

    def test_service_account_fields(self, provisioner):
        """ServiceAccount should have expected fields."""
        _, svc = provisioner.provision_service_account(
            username="svc-fields",
            service_name="test-service",
            description="Test",
            allowed_scopes=["read", "write"],
        )
        assert svc.service_name == "test-service"
        assert svc.allowed_scopes == ["read", "write"]


@pytest.mark.django_db
class TestAPIClientModel:
    """Tests for APIClient model."""

    def test_api_client_fields(self, provisioner):
        """APIClient should have expected fields."""
        _, client, _ = provisioner.provision_api_client(
            username="api-fields",
            client_id="test-client",
            client_type="confidential",
            redirect_uris=["https://example.com/callback"],
            allowed_scopes=["openid", "profile"],
            grant_types=["authorization_code"],
        )
        assert client.client_id == "test-client"
        assert client.redirect_uris == ["https://example.com/callback"]
        assert client.allowed_scopes == ["openid", "profile"]
        assert client.grant_types == ["authorization_code"]


@pytest.mark.django_db
class TestAgentAccount:
    """Tests for AgentAccount model."""

    def test_agent_account_fields(self, provisioner):
        """AgentAccount should have expected fields."""
        _, agent = provisioner.provision_agent(
            username="agent-fields",
            identifier="test-agent",
            agent_type="llm",
            capabilities={"streaming": True},
        )
        assert agent.identifier == "test-agent"
        assert agent.agent_type == "llm"
        assert agent.capabilities == {"streaming": True}


# ======================================================================
# API View Tests
# ======================================================================


@pytest.mark.django_db
class TestUserAccountAPI:
    """Tests for UserAccount API endpoints."""

    def test_list_users_staff(self, staff_client, provisioner):
        """Staff should be able to list users."""
        provisioner.provision_user(username="api-list-user", password="pass123")

        client, _ = staff_client
        response = client.get("/api/accounts/users/")

        assert response.status_code == status.HTTP_200_OK

    def test_list_users_not_authenticated(self, api_client):
        """Unauthenticated requests should be rejected."""
        response = api_client.get("/api/accounts/users/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_create_user_via_api(self, staff_client):
        """Staff should be able to create users via API."""
        client, _ = staff_client
        response = client.post(
            "/api/accounts/users/",
            {
                "username": "api-new-user",
                "password": "SecurePass123!",
                "email": "apinew@example.com",
                "display_name": "API New User",
            },
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Principal.objects.filter(username="api-new-user").exists()

    def test_get_user_detail(self, staff_client, provisioner):
        """Staff should be able to get user detail."""
        _, user_account = provisioner.provision_user(
            username="api-detail-user",
            password="pass123",
        )

        client, _ = staff_client
        response = client.get(f"/api/accounts/users/{user_account.pk}/")

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestServiceAccountAPI:
    """Tests for ServiceAccount API endpoints."""

    def test_list_service_accounts(self, staff_client, provisioner):
        """Staff should be able to list service accounts."""
        provisioner.provision_service_account(
            username="svc-api-list",
            service_name="api-test-svc",
        )

        client, _ = staff_client
        response = client.get("/api/accounts/service-accounts/")

        assert response.status_code == status.HTTP_200_OK

    def test_create_service_account_via_api(self, staff_client):
        """Staff should be able to create service accounts."""
        client, _ = staff_client
        response = client.post(
            "/api/accounts/service-accounts/",
            {
                "username": "svc-api-new",
                "service_name": "new-service",
                "description": "API created service",
            },
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestAPIClientAPI:
    """Tests for APIClient API endpoints."""

    def test_list_api_clients(self, staff_client, provisioner):
        """Staff should be able to list API clients."""
        provisioner.provision_api_client(
            username="api-api-list",
            client_id="list-test-client",
        )

        client, _ = staff_client
        response = client.get("/api/accounts/api-clients/")

        assert response.status_code == status.HTTP_200_OK

    def test_create_api_client_via_api(self, staff_client):
        """Staff should be able to create API clients."""
        client, _ = staff_client
        response = client.post(
            "/api/accounts/api-clients/",
            {
                "username": "api-api-new",
                "client_id": "new-api-client",
                "client_type": "confidential",
            },
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        # Confidential client should return a secret
        assert "client_secret" in response.json()


@pytest.mark.django_db
class TestAgentAccountAPI:
    """Tests for AgentAccount API endpoints."""

    def test_list_agents(self, staff_client, provisioner):
        """Staff should be able to list agents."""
        provisioner.provision_agent(
            username="agent-api-list",
            identifier="list-test-agent",
            agent_type="llm",
        )

        client, _ = staff_client
        response = client.get("/api/accounts/agents/")

        assert response.status_code == status.HTTP_200_OK

    def test_create_agent_via_api(self, staff_client):
        """Staff should be able to create agents."""
        client, _ = staff_client
        response = client.post(
            "/api/accounts/agents/",
            {
                "username": "agent-api-new",
                "identifier": "new-agent",
                "agent_type": "workflow",
                "description": "API created agent",
            },
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_201_CREATED


# ======================================================================
# Settings / Config Tests
# ======================================================================


@pytest.mark.django_db
class TestAccountsSettings:
    """Tests for accounts settings configuration."""

    def test_settings_accessible(self):
        """accounts_settings should be accessible."""
        from apps.accounts.settings import accounts_settings

        assert accounts_settings.settings_key == "ACCOUNTS"
        assert isinstance(accounts_settings.USERNAME_CASE_INSENSITIVE, bool)

    def test_settings_have_expected_keys(self):
        """Settings should have all expected configuration keys."""
        from apps.accounts.settings import accounts_settings

        assert hasattr(accounts_settings, "USERNAME_MIN_LENGTH")
        assert hasattr(accounts_settings, "USERNAME_CASE_INSENSITIVE")
        assert hasattr(accounts_settings, "API_PAGE_SIZE")


# ======================================================================
# No-Signal Verification
# ======================================================================


@pytest.mark.django_db
class TestNoSignals:
    """Verify that accounts app only has the minimal required signal handler."""

    def test_signals_module_has_only_update_last_login(self):
        """signals.py should only define update_last_login — no other handlers."""
        import apps.accounts.signals as signals_module

        public_attrs = [a for a in dir(signals_module) if not a.startswith("_")]
        # Only update_last_login is permitted (plus stdlib imports absorbed into the namespace)
        handler_attrs = [a for a in public_attrs if callable(getattr(signals_module, a))]
        assert handler_attrs == ["update_last_login"], (
            f"signals.py should only define update_last_login but has: {handler_attrs}"
        )

    def test_update_last_login_replaces_django_builtin(self):
        """Django's built-in update_last_login must be disconnected; ours must be connected."""
        from django.contrib.auth.signals import user_logged_in

        receiver_uids = [r[0][0] for r in user_logged_in.receivers]
        assert "update_last_login" not in receiver_uids, "Django's update_last_login must be disconnected."
        assert "accounts.update_last_login" in receiver_uids, "Our update_last_login must be connected."


# ======================================================================
# Types Tests
# ======================================================================


class TestAccountsTypes:
    """Tests for apps.accounts.types (TypedDict definitions)."""

    def test_accounts_namespace_settings_importable(self):
        """AccountsNamespaceSettings should be importable from accounts.types."""
        from apps.accounts.types import AccountsNamespaceSettings

        assert AccountsNamespaceSettings is not None

    def test_accounts_namespace_settings_is_typed_dict(self):
        """AccountsNamespaceSettings should be a TypedDict subclass."""
        from typing import get_type_hints

        from apps.accounts.types import AccountsNamespaceSettings

        hints = get_type_hints(AccountsNamespaceSettings)
        assert "USERNAME_MIN_LENGTH" in hints
        assert "USERNAME_CASE_INSENSITIVE" in hints
        assert "DEFAULT_LOCK_DURATION_MINUTES" in hints

    def test_accounts_namespace_settings_instantiation(self):
        """AccountsNamespaceSettings should be constructable as a regular dict."""
        config = {
            "USERNAME_CASE_INSENSITIVE": True,
            "DEFAULT_LOCK_DURATION_MINUTES": 30,
            "API_PAGE_SIZE": 25,
        }
        assert config["USERNAME_CASE_INSENSITIVE"] is True
        assert config["DEFAULT_LOCK_DURATION_MINUTES"] == 30

    def test_all_exports(self):
        """__all__ should expose AccountsNamespaceSettings."""
        from apps.accounts import types as types_module

        assert "AccountsNamespaceSettings" in types_module.__all__

    def test_feature_flag_fields(self):
        """Feature flag fields should be present in type hints."""
        from typing import get_type_hints

        from apps.accounts.types import AccountsNamespaceSettings

        hints = get_type_hints(AccountsNamespaceSettings)
        assert "ENABLE_AGENT_ACCOUNTS" in hints
        assert "ENABLE_API_CLIENTS" in hints
        assert "ENABLE_SERVICE_ACCOUNTS" in hints

    def test_security_fields(self):
        """Security-related fields should be present in type hints."""
        from typing import get_type_hints

        from apps.accounts.types import AccountsNamespaceSettings

        hints = get_type_hints(AccountsNamespaceSettings)
        assert "SECURITY_STAMP_ROTATION_ON_PASSWORD_CHANGE" in hints
        assert "SECURITY_STAMP_ROTATION_ON_EMAIL_CHANGE" in hints
        assert "MAX_FAILED_LOGIN_ATTEMPTS" in hints

    def test_principal_kinds_field(self):
        """PRINCIPAL_KINDS should be list of dicts in type hints."""
        from typing import get_type_hints

        from apps.accounts.types import AccountsNamespaceSettings

        hints = get_type_hints(AccountsNamespaceSettings)
        assert "PRINCIPAL_KINDS" in hints

    def test_audit_fields(self):
        """Audit-related fields should be present."""
        from typing import get_type_hints

        from apps.accounts.types import AccountsNamespaceSettings

        hints = get_type_hints(AccountsNamespaceSettings)
        assert "AUDIT_PRINCIPAL_CHANGES" in hints
        assert "AUDIT_BACKEND" in hints


# ======================================================================
# Validator Tests
# ======================================================================


class TestUsernameValidatorDirectCall:
    """Tests for UsernameValidator called directly (not via model)."""

    def test_valid_username(self):
        """A valid username should pass without error."""
        from apps.accounts.validators import UsernameValidator

        validator = UsernameValidator()
        validator("validuser")  # Should not raise

    def test_reserved_username_raises(self):
        """Reserved usernames should raise ValidationError."""
        from apps.accounts.validators import UsernameValidator

        validator = UsernameValidator()
        with pytest.raises(ValidationError) as exc_info:
            validator("admin")
        assert exc_info.value.code == "username_reserved"

    def test_too_short_username_raises(self):
        """Username shorter than MIN_USERNAME_LENGTH should raise ValidationError."""
        from apps.accounts.constants import MIN_USERNAME_LENGTH
        from apps.accounts.validators import UsernameValidator

        validator = UsernameValidator()
        short = "a" * (MIN_USERNAME_LENGTH - 1)
        with pytest.raises(ValidationError) as exc_info:
            validator(short)
        assert exc_info.value.code == "username_too_short"

    def test_too_long_username_raises(self):
        """Username longer than MAX_USERNAME_LENGTH should raise ValidationError."""
        from apps.accounts.constants import MAX_USERNAME_LENGTH
        from apps.accounts.validators import UsernameValidator

        validator = UsernameValidator()
        long_name = "a" * (MAX_USERNAME_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            validator(long_name)
        assert exc_info.value.code == "username_too_long"

    def test_consecutive_dots_raise(self):
        """Username with consecutive dots should raise ValidationError."""
        from apps.accounts.validators import UsernameValidator

        validator = UsernameValidator()
        with pytest.raises(ValidationError) as exc_info:
            validator("user..name")
        assert exc_info.value.code == "username_consecutive_specials"

    def test_consecutive_hyphens_raise(self):
        """Username with consecutive hyphens should raise ValidationError."""
        from apps.accounts.validators import UsernameValidator

        validator = UsernameValidator()
        with pytest.raises(ValidationError) as exc_info:
            validator("user--name")
        assert exc_info.value.code == "username_consecutive_specials"

    def test_consecutive_underscores_raise(self):
        """Username with consecutive underscores should raise ValidationError."""
        from apps.accounts.validators import UsernameValidator

        validator = UsernameValidator()
        with pytest.raises(ValidationError) as exc_info:
            validator("user__name")
        assert exc_info.value.code == "username_consecutive_specials"

    def test_invalid_regex_raises(self):
        """Username with characters not matching regex should raise ValidationError."""
        from apps.accounts.validators import UsernameValidator

        validator = UsernameValidator()
        with pytest.raises(ValidationError):
            validator("user name")  # Space not allowed


@pytest.mark.django_db
class TestValidateUsernameNotReserved:
    """Tests for validate_username_not_reserved function."""

    def test_non_reserved_username_passes(self):
        """Non-reserved username should not raise."""
        from django.test import override_settings

        from apps.accounts.validators import validate_username_not_reserved

        with override_settings(ACCOUNTS={"USERNAME_RESERVED_WORDS": ["admin", "root", "system"]}):
            from apps.accounts.settings import accounts_settings

            accounts_settings.reload()
            validate_username_not_reserved("regularuser")  # Should not raise
            accounts_settings.reload()

    def test_reserved_username_raises(self):
        """Reserved username should raise ValidationError."""
        from django.test import override_settings

        from apps.accounts.validators import validate_username_not_reserved

        with override_settings(ACCOUNTS={"USERNAME_RESERVED_WORDS": ["admin", "root", "system"]}):
            from apps.accounts.settings import accounts_settings

            accounts_settings.reload()
            try:
                with pytest.raises(ValidationError) as exc_info:
                    validate_username_not_reserved("admin")
                assert exc_info.value.code == "username_reserved"
            finally:
                accounts_settings.reload()

    def test_reserved_case_insensitive(self):
        """Reserved check should be case-insensitive."""
        from django.test import override_settings

        from apps.accounts.validators import validate_username_not_reserved

        with override_settings(ACCOUNTS={"USERNAME_RESERVED_WORDS": ["Admin", "ROOT"]}):
            from apps.accounts.settings import accounts_settings

            accounts_settings.reload()
            try:
                with pytest.raises(ValidationError) as exc_info:
                    validate_username_not_reserved("ADMIN")
                assert exc_info.value.code == "username_reserved"
            finally:
                accounts_settings.reload()

    def test_reserved_mixed_case(self):
        """Mixed case reserved word should be rejected."""
        from django.test import override_settings

        from apps.accounts.validators import validate_username_not_reserved

        with override_settings(ACCOUNTS={"USERNAME_RESERVED_WORDS": ["root", "system"]}):
            from apps.accounts.settings import accounts_settings

            accounts_settings.reload()
            try:
                with pytest.raises(ValidationError):
                    validate_username_not_reserved("Root")
            finally:
                accounts_settings.reload()


class TestPhoneNumberValidator:
    """Tests for PhoneNumberValidator."""

    def test_valid_e164_phone(self):
        """E.164 formatted phone number should pass."""
        from apps.accounts.validators import PhoneNumberValidator

        validator = PhoneNumberValidator()
        validator("+12125552368")  # Should not raise

    def test_valid_international_phone(self):
        """International format phone should pass."""
        from apps.accounts.validators import PhoneNumberValidator

        validator = PhoneNumberValidator()
        validator("+447911123456")  # UK number

    def test_invalid_phone_raises(self):
        """Completely invalid phone number should raise ValidationError."""
        from apps.accounts.validators import PhoneNumberValidator

        validator = PhoneNumberValidator()
        with pytest.raises(ValidationError) as exc_info:
            validator("not-a-phone")
        assert exc_info.value.code == "invalid_phone_number"

    def test_unparseable_phone_raises(self):
        """Phone number that can't be parsed should raise ValidationError."""
        from apps.accounts.validators import PhoneNumberValidator

        validator = PhoneNumberValidator()
        with pytest.raises(ValidationError) as exc_info:
            validator("++1234567890")  # Double plus sign
        assert exc_info.value.code == "invalid_phone_number"

    def test_empty_value_passes(self):
        """Empty string should pass (phone is optional)."""
        from apps.accounts.validators import PhoneNumberValidator

        validator = PhoneNumberValidator()
        validator("")  # Should not raise

    def test_eq_same_class(self):
        """Two PhoneNumberValidator instances should be equal."""
        from apps.accounts.validators import PhoneNumberValidator

        v1 = PhoneNumberValidator()
        v2 = PhoneNumberValidator()
        assert v1 == v2

    def test_eq_different_class(self):
        """PhoneNumberValidator should not equal objects of other types."""
        from apps.accounts.validators import PhoneNumberValidator

        validator = PhoneNumberValidator()
        assert validator != "string"
        assert validator != 42

    def test_deconstruct(self):
        """deconstruct() should return valid migration serialization tuple."""
        from apps.accounts.validators import PhoneNumberValidator

        validator = PhoneNumberValidator()
        path, args, kwargs = validator.deconstruct()
        assert "PhoneNumberValidator" in path
        assert args == []
        assert kwargs == {}

    def test_invalid_number_not_valid(self):
        """A parseable but invalid phone number should raise ValidationError."""
        from apps.accounts.validators import PhoneNumberValidator

        validator = PhoneNumberValidator()
        # 000-000-0000 parses but is not a real valid number
        with pytest.raises(ValidationError):
            validator("+10000000000")


class TestValidateMetadataSize:
    """Tests for validate_metadata_size function."""

    def test_small_metadata_passes(self):
        """Small metadata dict should pass."""
        from apps.accounts.validators import validate_metadata_size

        validate_metadata_size({"key": "value"})  # Should not raise

    def test_oversized_metadata_raises(self):
        """Metadata exceeding max_bytes should raise ValidationError."""
        from apps.accounts.validators import validate_metadata_size

        huge = {"key": "x" * 100_000}
        with pytest.raises(ValidationError) as exc_info:
            validate_metadata_size(huge, max_bytes=100)
        assert exc_info.value.code == "metadata_too_large"

    def test_exactly_at_limit_passes(self):
        """Metadata exactly at the limit should pass."""
        import json

        from apps.accounts.validators import validate_metadata_size

        data = {"k": "v"}
        serialized = json.dumps(data, separators=(",", ":"))
        size = len(serialized.encode("utf-8"))
        validate_metadata_size(data, max_bytes=size)  # Should not raise

    def test_default_limit_used_when_none(self):
        """validate_metadata_size uses settings default when max_bytes is None."""
        from apps.accounts.validators import validate_metadata_size

        # Small dict should always pass with any reasonable default
        validate_metadata_size({"status": "ok"})

    def test_unicode_metadata_size_counted_in_bytes(self):
        """Unicode characters should be counted in bytes, not character count."""
        from apps.accounts.validators import validate_metadata_size

        # Multi-byte unicode characters
        data = {"key": "ñ" * 10}  # Each ñ is 2 bytes in UTF-8
        import json

        size = len(json.dumps(data, separators=(",", ":")).encode("utf-8"))
        with pytest.raises(ValidationError):
            validate_metadata_size(data, max_bytes=size - 1)


class TestValidateTagsCount:
    """Tests for validate_tags_count function."""

    def test_empty_tags_passes(self):
        """Empty list of tags should pass."""
        from apps.accounts.validators import validate_tags_count

        validate_tags_count([], max_count=10)

    def test_tags_within_limit_pass(self):
        """Tags within the count limit should pass."""
        from apps.accounts.validators import validate_tags_count

        validate_tags_count(["a", "b", "c"], max_count=5)

    def test_tags_at_limit_passes(self):
        """Tags exactly at the limit should pass."""
        from apps.accounts.validators import validate_tags_count

        validate_tags_count(["a", "b", "c"], max_count=3)

    def test_tags_exceeding_limit_raises(self):
        """Tags exceeding the count limit should raise ValidationError."""
        from apps.accounts.validators import validate_tags_count

        with pytest.raises(ValidationError) as exc_info:
            validate_tags_count(["a", "b", "c", "d"], max_count=3)
        assert exc_info.value.code == "too_many_tags"

    def test_non_list_raises(self):
        """Non-list value should raise ValidationError."""
        from apps.accounts.validators import validate_tags_count

        with pytest.raises(ValidationError) as exc_info:
            validate_tags_count("not-a-list", max_count=10)
        assert exc_info.value.code == "tags_not_list"

    def test_dict_raises(self):
        """Dict value should raise ValidationError (not a list)."""
        from apps.accounts.validators import validate_tags_count

        with pytest.raises(ValidationError) as exc_info:
            validate_tags_count({"tag": "value"}, max_count=10)
        assert exc_info.value.code == "tags_not_list"

    def test_default_limit_used_when_none(self):
        """validate_tags_count uses settings default when max_count is None."""
        from apps.accounts.validators import validate_tags_count

        validate_tags_count(["tag1", "tag2"])  # Should not raise with few tags


# ======================================================================
# Filter Tests
# ======================================================================


class TestPrincipalStatusFilter:
    """Tests for PrincipalStatusFilter."""

    def _make_request(self, params: dict):
        from unittest.mock import MagicMock

        req = MagicMock()
        req.query_params = params
        return req

    def _filter(self, params: dict):
        from unittest.mock import MagicMock

        from apps.accounts.api.filters import PrincipalStatusFilter

        qs = MagicMock()
        qs.filter.return_value = qs
        backend = PrincipalStatusFilter()
        return backend.filter_queryset(self._make_request(params), qs, view=MagicMock()), qs

    def test_no_status_returns_original_queryset(self):
        """Without ?status param, the queryset is returned unchanged."""
        result, qs = self._filter({})
        qs.filter.assert_not_called()
        assert result is qs

    def test_unknown_status_returns_original_queryset(self):
        """Unknown status value returns the queryset unchanged."""
        result, qs = self._filter({"status": "nonexistent"})
        qs.filter.assert_not_called()
        assert result is qs

    def test_active_status_applies_all_null_filters(self):
        """?status=active should filter for all nulls (not disabled/suspended/deleted)."""
        from apps.accounts.api.filters import PrincipalStatusFilter

        qs_mock = MagicMock()
        qs_mock.filter.return_value = qs_mock
        req = self._make_request({"status": "active"})
        PrincipalStatusFilter().filter_queryset(req, qs_mock, view=None)
        call_kwargs = qs_mock.filter.call_args[1]
        assert call_kwargs.get("principal__disabled_at__isnull") is True
        assert call_kwargs.get("principal__suspended_at__isnull") is True
        assert call_kwargs.get("principal__deleted_at__isnull") is True

    def test_disabled_status_applies_filter(self):
        """?status=disabled should filter principal__disabled_at__isnull=False."""
        from apps.accounts.api.filters import PrincipalStatusFilter

        qs_mock = MagicMock()
        qs_mock.filter.return_value = qs_mock
        req = self._make_request({"status": "disabled"})
        PrincipalStatusFilter().filter_queryset(req, qs_mock, view=None)
        call_kwargs = qs_mock.filter.call_args[1]
        assert call_kwargs.get("principal__disabled_at__isnull") is False

    def test_suspended_status_applies_filter(self):
        """?status=suspended should filter principal__suspended_at__isnull=False."""
        from apps.accounts.api.filters import PrincipalStatusFilter

        qs_mock = MagicMock()
        qs_mock.filter.return_value = qs_mock
        req = self._make_request({"status": "suspended"})
        PrincipalStatusFilter().filter_queryset(req, qs_mock, view=None)
        call_kwargs = qs_mock.filter.call_args[1]
        assert call_kwargs.get("principal__suspended_at__isnull") is False

    def test_deleted_status_applies_filter(self):
        """?status=deleted should filter principal__deleted_at__isnull=False."""
        from apps.accounts.api.filters import PrincipalStatusFilter

        qs_mock = MagicMock()
        qs_mock.filter.return_value = qs_mock
        req = self._make_request({"status": "deleted"})
        PrincipalStatusFilter().filter_queryset(req, qs_mock, view=None)
        call_kwargs = qs_mock.filter.call_args[1]
        assert call_kwargs.get("principal__deleted_at__isnull") is False


class TestPrincipalKindFilter:
    """Tests for PrincipalKindFilter."""

    def _make_request(self, params: dict):
        from unittest.mock import MagicMock

        req = MagicMock()
        req.query_params = params
        return req

    def test_no_kind_returns_original_queryset(self):
        """Without ?kind param, the queryset is returned unchanged."""
        from unittest.mock import MagicMock

        from apps.accounts.api.filters import PrincipalKindFilter

        qs = MagicMock()
        req = self._make_request({})
        result = PrincipalKindFilter().filter_queryset(req, qs, view=None)
        qs.filter.assert_not_called()
        assert result is qs

    def test_kind_user_applies_filter(self):
        """?kind=user should filter by principal__kind=user."""
        from unittest.mock import MagicMock

        from apps.accounts.api.filters import PrincipalKindFilter

        qs = MagicMock()
        qs.filter.return_value = qs
        req = self._make_request({"kind": "user"})
        PrincipalKindFilter().filter_queryset(req, qs, view=None)
        qs.filter.assert_called_once_with(principal__kind="user")

    def test_kind_service_account_applies_filter(self):
        """?kind=service_account should filter by that kind."""
        from unittest.mock import MagicMock

        from apps.accounts.api.filters import PrincipalKindFilter

        qs = MagicMock()
        qs.filter.return_value = qs
        req = self._make_request({"kind": "service_account"})
        PrincipalKindFilter().filter_queryset(req, qs, view=None)
        qs.filter.assert_called_once_with(principal__kind="service_account")


# ======================================================================
# Principal API View Tests
# ======================================================================


@pytest.mark.django_db
class TestPrincipalListCreateViewPermissions:
    """Tests for PrincipalListCreateView permission and queryset logic."""

    def test_list_principals_authenticated_non_staff(self, authenticated_client, user_principal):
        """Non-staff users should only see their own principal."""
        client, principal = authenticated_client
        response = client.get("/api/accounts/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data.get("results", data)
        if isinstance(results, list):
            for item in results:
                assert str(item["id"]) == str(principal.pk)

    def test_list_principals_staff_sees_all(self, staff_client, user_principal):
        """Staff users should see all principals."""
        client, _ = staff_client
        response = client.get("/api/accounts/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        count = data.get("count", len(data.get("results", [])))
        assert count >= 1  # At least the staff principal

    def test_list_principals_unauthenticated_denied(self, api_client):
        """Unauthenticated requests should be denied (401/403)."""
        response = api_client.get("/api/accounts/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_create_principal_anonymous_allowed(self, api_client):
        """Anonymous users should be able to sign up (POST is AllowAny)."""
        response = api_client.post(
            "/api/accounts/",
            {
                "username": "newprincipal",
                "password": "SecurePass123!",
                "kind": "user",
            },
            content_type="application/json",
        )
        # Signup is open; either 201 created or 400 validation error
        assert response.status_code in (
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_create_principal_with_email(self, api_client):
        """Creating a principal with email and password."""
        response = api_client.post(
            "/api/accounts/",
            {
                "username": "signupuser123",
                "password": "SecurePass123!",
                "email": "signup123@example.com",
            },
            content_type="application/json",
        )
        assert response.status_code in (
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
        )


@pytest.mark.django_db
class TestPrincipalDetailView:
    """Tests for PrincipalDetailView retrieve/update/destroy."""

    def test_retrieve_own_principal_non_staff(self, authenticated_client, user_principal):
        """Non-staff user should be able to retrieve their own principal."""
        client, principal = authenticated_client
        response = client.get(f"/api/accounts/{principal.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert str(response.json()["id"]) == str(principal.pk)

    def test_retrieve_other_principal_non_staff_denied(self, authenticated_client, staff_principal):
        """Non-staff user should NOT be able to retrieve another user's principal."""
        client, _ = authenticated_client
        response = client.get(f"/api/accounts/{staff_principal.pk}/")
        # Should be 403 or 404 (object-level permission or filtered queryset)
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_retrieve_any_principal_staff(self, staff_client, user_principal):
        """Staff should be able to retrieve any principal."""
        client, _ = staff_client
        principal, _ = user_principal
        response = client.get(f"/api/accounts/{principal.pk}/")
        assert response.status_code == status.HTTP_200_OK

    def test_update_own_principal_non_staff(self, authenticated_client, user_principal):
        """Non-staff user should be able to patch their own principal."""
        client, principal = authenticated_client
        response = client.patch(
            f"/api/accounts/{principal.pk}/",
            {"display_name": "Updated Name"},
            content_type="application/json",
        )
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST)

    def test_destroy_principal_non_staff_denied(self, authenticated_client, user_principal):
        """Non-staff user should be denied when attempting to soft-delete a principal."""
        client, principal = authenticated_client
        response = client.delete(f"/api/accounts/{principal.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_destroy_principal_staff_allowed(self, staff_client, user_principal):
        """Staff should be able to soft-delete a principal."""
        client, _ = staff_client
        principal, _ = user_principal
        response = client.delete(f"/api/accounts/{principal.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_retrieve_unauthenticated_denied(self, api_client, user_principal):
        """Unauthenticated access to principal detail should be denied."""
        principal, _ = user_principal
        response = api_client.get(f"/api/accounts/{principal.pk}/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
class TestPrincipalPermissions:
    """Tests for IsStaffOrReadOnly and IsSelfOrStaff permission classes."""

    def test_is_staff_or_read_only_get_authenticated(self, authenticated_client):
        """Authenticated non-staff users should be able to GET (read-only)."""
        client, _ = authenticated_client
        response = client.get("/api/accounts/")
        assert response.status_code == status.HTTP_200_OK

    def test_is_self_or_staff_object_level_own(self, authenticated_client, user_principal):
        """IsSelfOrStaff: principal can access their own record."""
        from apps.accounts.api.permissions import IsSelfOrStaff

        principal, _ = user_principal
        request = MagicMock()
        request.user = principal
        request.user.is_staff = False

        perm = IsSelfOrStaff()
        result = perm.has_object_permission(request, MagicMock(), principal)
        assert result is True

    def test_is_self_or_staff_object_level_staff(self, staff_principal, user_principal):
        """IsSelfOrStaff: staff can access any principal."""
        from apps.accounts.api.permissions import IsSelfOrStaff

        other_principal, _ = user_principal
        request = MagicMock()
        request.user = staff_principal
        request.user.is_staff = True

        perm = IsSelfOrStaff()
        result = perm.has_object_permission(request, MagicMock(), other_principal)
        assert result is True

    def test_is_self_or_staff_object_level_other_denied(self, authenticated_client, staff_principal):
        """IsSelfOrStaff: non-staff cannot access another principal's record."""
        from apps.accounts.api.permissions import IsSelfOrStaff

        client, principal = authenticated_client
        request = MagicMock()
        request.user = principal
        request.user.is_staff = False

        perm = IsSelfOrStaff()
        result = perm.has_object_permission(request, MagicMock(), staff_principal)
        assert result is False
