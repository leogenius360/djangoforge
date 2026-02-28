# Integration Guide — All Apps Working Together

This document explains how the six apps form a unified platform and provides
complete end-to-end workflow examples.

---

## App Dependency Graph

```
                    ┌───────────────────────────┐
                    │       apps/core            │
                    │  Base models, context,     │
                    │  health, crypto, mixins    │
                    └─────────────┬─────────────┘
                                  │ used by all apps
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│  apps/accounts  │   │  apps/auditing    │   │   apps/authz      │
│  Principal      │   │  Event, Registry, │   │  Permission, Role,│
│  UserAccount    │   │  create_audit_    │   │  Policy, Checker  │
│  ServiceAccount │   │  entry()          │   └────────┬──────────┘
│  Provisioner    │   └───────────────────┘            │
└────────┬────────┘                                    │
         │ AUTH_USER_MODEL = Principal                  │
         │                                             │
    ┌────▼────────────────────────────────────────┐    │
    │                apps/authn                    │    │
    │  AuthenticationService, MFAService,          │    │
    │  PasswordService, TokenService               │    │
    └────┬─────────────────────────────────────────┘    │
         │ creates sessions                             │
    ┌────▼─────────────────────────────────────────────-▼──┐
    │                   apps/sessions                       │
    │   AuthSession, DualAuthentication,                    │
    │   SessionTrackingMiddleware                           │
    └───────────────────────────────────────────────────────┘
```

### Dependency summary

| App | Depends on |
|---|---|
| `core` | Nothing (pure infrastructure) |
| `accounts` | `core` |
| `authn` | `core`, `accounts`, `sessions` |
| `sessions` | `core`, `accounts`, `authn` (enums only) |
| `authz` | `core`, `accounts` |
| `auditing` | `core`, `accounts` |

---

## URL Routing

```
/api/
  health/           ── core: HealthCheckView
  health/live/      ── core: LivenessProbeView
  health/ready/     ── core: ReadinessProbeView
  health/startup/   ── core: StartupProbeView
  metrics/          ── core: SystemMetricsView

  auth/             ── authn: authentication, password, MFA, verification
    login/
    login/mfa/
    logout/
    token/refresh/
    token/verify/
    password/change/
    password/reset/
    password/reset/confirm/
    mfa/status/
    mfa/setup/
    mfa/disable/
    mfa/backup-codes/
    passwordless/request/
    passwordless/verify/
    passwordless/totp/
    verify/email/request/
    verify/email/confirm/
    verify/phone/request/
    verify/phone/confirm/

  sessions/         ── sessions: session management
    (GET/DELETE)
    all/
    <uuid>/

  accounts/         ── accounts: identity management
    (principals, users, service accounts, API clients, agents)
    users/
    service-accounts/
    api-clients/
    agents/

  authz/            ── authz: authorization
    permissions/
    roles/
    assignments/
    policies/
    check/

  audit/            ── auditing: audit trail (staff-only)
    events/
    history/
    version/
```

---

## Middleware Stack

```python
# config/settings/base.py
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",   # 1. Resolve user
    "apps.sessions.middleware.SessionTrackingMiddleware",        # 2. Track activity
    "apps.core.middleware.ActorTrackingMiddleware",              # 3. Set actor context
    "apps.auditing.middleware.AuditingMiddleware",               # 4. Set audit context
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

**Middleware execution order matters:**
1. `AuthenticationMiddleware` — resolves `request.user` from JWT/cookie
2. `SessionTrackingMiddleware` — attaches `request.user_session`, updates `last_seen_at`
3. `ActorTrackingMiddleware` — sets `core.context` actor for model saves
4. `AuditingMiddleware` — sets `auditing.context` with actor + IP + request_id

---

## End-to-End Workflows

### 1. User Registration + Onboarding

```python
# apps/accounts/services/provisioning.py
from apps.accounts.services import AccountProvisioner
from apps.auditing.services import create_audit_entry, serialize_model_state
from apps.auditing.enums import EventType
from apps.core.context import set_current_actor

provisioner = AccountProvisioner()

# Step 1: Provision Principal + UserAccount atomically
principal, user = provisioner.provision_user(
    username="jdoe",
    password="Secr3t!Pass",
    email="jdoe@example.com",
    display_name="Jane Doe",
)
# Both rows are created inside transaction.atomic()
# Principal.kind = "user", UserAccount.principal = principal

# Step 2: Request email verification
from apps.authn.services.verification import VerificationService
# (called after provisioning, token sent out-of-band)
VerificationService.request_email_verification(principal, request=request)

# Step 3: User clicks verification link
VerificationService.confirm_email_verification(principal, token="<token-from-email>")
# principal.email_verified_at is now set

# Step 4: Auto-audit the provisioning (if not using AuditableModelMixin)
with set_current_actor(principal):
    state = serialize_model_state(principal)
    create_audit_entry(principal, EventType.CREATE, state, actor=principal)
```

---

### 2. Password Login (Full Flow)

```
Client                    API                  Services
  │                        │                       │
  ├── POST /api/auth/login/ ─► LoginView            │
  │   {identifier, password}                        │
  │                        ├── AuthenticationService.authenticate_with_password()
  │                        │       │                │
  │                        │       ├── django.authenticate() ──► EmailBackend
  │                        │       │   resolves principal, checks password
  │                        │       │                │
  │                        │       ├── LockoutService.check_lockout()
  │                        │       │   raises AccountLockedError if locked
  │                        │       │                │
  │                        │       ├── Check MFA → MFARequiredError if enabled
  │                        │       │                │
  │                        │       └── AuthSession.objects.create_session()
  │                        │           issues JWT + session record
  │                        │                        │
  │◄── 200 {access, refresh, session_id} ───────────│
  │                        │                        │
  │   (all subsequent requests include JWT header)  │
  │                        │                        │
  ├── GET /api/projects/ ──► any view               │
  │   Authorization: Bearer <access>                │
  │                        │                        │
  │                DualAuthentication               │
  │                validates JWT,                   │
  │                loads AuthSession                │
  │                        │                        │
  │          SessionTrackingMiddleware              │
  │          updates last_seen_at                   │
  │                        │                        │
  │◄── 200 {projects...} ──────────────────────────-┤
```

**Code:**

```python
# In LoginView
from apps.authn.services.authentication import AuthenticationService
from apps.authn.exceptions import MFARequiredError, AccountLockedError, InvalidCredentialsError

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        identifier = request.data["identifier"]
        password = request.data["password"]

        try:
            result = AuthenticationService.authenticate_with_password(
                request=request,
                identifier=identifier,
                password=password,
            )
            return Response({
                "access": result.access_token,
                "refresh": result.refresh_token,
                "expires_in": result.expires_in,
                "session_id": str(result.session.pk),
            })

        except MFARequiredError as exc:
            return Response({
                "mfa_required": True,
                "mfa_token": exc.mfa_token,
            }, status=200)

        except AccountLockedError:
            return Response({"error": "Account is temporarily locked."}, status=423)

        except InvalidCredentialsError:
            return Response({"error": "Invalid credentials."}, status=401)
```

---

### 3. MFA Login (Two-Factor Flow)

```python
# Step 1: Password login → MFARequiredError
response = client.post("/api/auth/login/", {
    "identifier": "jdoe@example.com",
    "password": "Secr3t!Pass",
})
# Response:
# {"mfa_required": true, "mfa_token": "abc123def456"}

# Step 2: User opens authenticator app, reads 6-digit code

# Step 3: Complete MFA
response = client.post("/api/auth/login/mfa/", {
    "mfa_token": "abc123def456",
    "code": "123456",   # TOTP or backup code
})
# Response:
# {"access": "eyJ...", "refresh": "eyJ...", "session_id": "..."}
```

**Behind the scenes:**
1. `AuthenticationService.authenticate_with_password` creates `MFAPendingAuthentication`
2. Returns `MFARequiredError` with the raw MFA token
3. `AuthenticationService.authenticate_mfa` verifies the TOTP code via `MFAService`
4. On success, creates `AuthSession` and issues JWT

---

### 4. Authorization Check in a View

```python
# In a view that protects a resource
from apps.authz.services import AuthorizationChecker
from apps.authz.exceptions import PermissionDeniedError

checker = AuthorizationChecker()

class ProjectUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        # Check RBAC + ABAC
        decision = checker.check(request.user, "update", project)
        if not decision.allowed:
            return Response(
                {"error": "Permission denied", "reason": decision.reason},
                status=403,
            )

        # Proceed with update
        serializer = ProjectSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Audit the change
        from apps.auditing.services import create_audit_entry, serialize_model_state
        from apps.auditing.enums import EventType

        pre_state = serialize_model_state(project)
        instance = serializer.instance
        post_state = serialize_model_state(instance)
        create_audit_entry(
            instance,
            EventType.UPDATE,
            post_state,
            pre_state=pre_state,
            actor=request.user,
            comment=f"Updated via API by {request.user.username}",
        )

        return Response(serializer.data)
```

---

### 5. Complete Security Incident Response

```python
"""
Scenario: Suspicious activity detected on a user account.
Steps:
  1. Lock the account → invalidates all sessions
  2. Force-revoke all active sessions
  3. Create an audit event for the action
  4. Send alert to security team
"""
from apps.accounts.models import Principal
from apps.sessions.models import AuthSession
from apps.auditing.services import create_audit_entry, serialize_model_state
from apps.auditing.enums import EventType
from apps.core.context import set_current_actor
from datetime import timedelta


def handle_security_incident(
    suspect_principal: Principal,
    admin_principal: Principal,
    reason: str,
):
    with set_current_actor(admin_principal):
        # 1. Lock account (bumps security_stamp → invalidates all JWTs)
        suspect_principal.lock(
            actor=admin_principal,
            reason=reason,
            duration=timedelta(hours=24),
        )

        # 2. Force-revoke all active sessions
        revoked_count = AuthSession.terminate_all_for_principal(
            suspect_principal,
            reason=f"Security lock: {reason}",
            actor=admin_principal,
        )

        # 3. Audit the incident response
        state = serialize_model_state(suspect_principal)
        create_audit_entry(
            suspect_principal,
            EventType.CUSTOM,
            state,
            actor=admin_principal,
            comment=f"Security incident: {reason}. {revoked_count} sessions revoked.",
        )

    # 4. Alert security team (out-of-band)
    notify_security_team(suspect_principal, reason=reason)

    return revoked_count
```

---

### 6. Service Account + API Client Setup

```python
"""
Setting up a machine-to-machine integration:
  - Provision a ServiceAccount
  - Assign it the "payments.read" role on a specific resource
  - Create an AuthSession for the service account
  - Audit the provisioning
"""
from apps.accounts.services import AccountProvisioner
from apps.authz.services import AssignmentService, RoleService
from apps.sessions.models import AuthSession
from apps.auditing.services import create_audit_entry, serialize_model_state
from apps.auditing.enums import EventType
from apps.core.context import set_current_actor


def setup_payment_integration(admin_principal, payment_resource):
    provisioner = AccountProvisioner()
    assign_svc = AssignmentService()

    # 1. Provision service account
    principal, svc = provisioner.provision_service_account(
        service_name="payment-gateway",
        name="Payment Gateway",
        description="External payment processing service",
        allowed_scopes=["payments.read", "payments.write"],
        owner=admin_principal,
    )

    # 2. Assign the required role on the payment resource
    assignment = assign_svc.assign_role(
        principal=principal,
        role=RoleService().get_by_codename("payments.processor"),
        resource=payment_resource,
        granted_by=admin_principal,
        reason="M2M payment integration",
    )

    # 3. Create a service session
    session = AuthSession.create_session(
        principal=principal,
        channel="service",
        auth_method="api_key",
        ip_address="10.0.0.1",
    )

    # 4. Audit
    with set_current_actor(admin_principal):
        state = serialize_model_state(principal)
        create_audit_entry(
            principal,
            EventType.CREATE,
            state,
            actor=admin_principal,
            comment="Payment gateway service account provisioned",
        )

    return principal, svc, session
```

---

### 7. Password Reset Flow

```
Client                   API                   Services
  │                       │                        │
  ├── POST /api/auth/password/reset/ ──────────────►
  │   {"email": "jdoe@example.com"}                │
  │                       │                        │
  │             PasswordService.request_reset()     │
  │             (always 200, never leaks existence) │
  │             TokenService.create_token()         │
  │             → token emailed out-of-band         │
  │◄── 200 ──────────────────────────────────────--|
  │                       │                        │
  │  [User receives email with link containing token]
  │                       │                        │
  ├── POST /api/auth/password/reset/confirm/ ───────►
  │   {"token": "...", "new_password": "..."}      │
  │                       │                        │
  │             PasswordService.confirm_reset()     │
  │             TokenService.consume_token()        │
  │             Principal.set_password()            │
  │             principal.bump_security_stamp()     │
  │             → all sessions invalidated          │
  │◄── 200 ──────────────────────────────────────--|
```

---

### 8. Audit Trail Query

```python
# Retrieve complete history of a project
from apps.auditing.services import get_object_history, get_version

history = get_object_history(Project, pk=project_id)

for event in history:
    print(f"v{event.version:3d} | {event.event_type:8s} | "
          f"{event.actor.username if event.actor else 'system':20s} | "
          f"{event.created_at:%Y-%m-%d %H:%M} | "
          f"{event.comment or '(no comment)'}")

# Output:
# v  1 | create   | admin                | 2024-01-10 09:00 | Created via provisioner
# v  2 | update   | jdoe                 | 2024-01-10 14:30 | Updated description
# v  3 | update   | jdoe                 | 2024-01-12 10:15 | Status changed to active
# v  4 | update   | admin                | 2024-01-15 16:00 | Security review update

# Get state at version 2
state_v2 = get_version(Project, pk=project_id, version_number=2)
print(state_v2["description"])   # value at v2

# Undo last change
from apps.auditing.services import undo_change
last_event = history[-1]
undo_event = undo_change(last_event)
# Project restored to v3 state; v5 UNDO event created
```

---

## Cross-App Data Flow Diagrams

### Authentication Data Flow

```
HTTP Request
     │
     ▼
DualAuthentication.authenticate()
     │
     ├── JWT path: validates token → loads Principal from token claims
     │   └── loads AuthSession by session_id claim
     │
     └── Cookie path: loads Django session → resolves AuthSession
                      loads Principal from AuthSession.principal

AuthSession loaded → SessionTrackingMiddleware:
     - session.touch_activity(ip_address, path)
     - request.user_session = session

ActorTrackingMiddleware:
     - set_current_actor(request.user)  → available for model saves

AuditingMiddleware:
     - sets auditing contextvars (actor, ip, user_agent, request_id)
     - available for create_audit_entry() calls
```

### Model Save Data Flow

```
model_instance.save()
     │
     ▼
ModelOperationsMixin.save()
     ├── LifecycleValidator.validate()     (consistency checks)
     ├── actor = get_current_actor()        (from ActorTrackingMiddleware)
     ├── instance.created_by = actor        (if BaseActorMixin + new instance)
     ├── instance.updated_by = actor        (if BaseActorMixin)
     ├── version check (optimistic lock)    (if version field present)
     └── DB INSERT/UPDATE

If AuditableModelMixin:
     ├── pre_state captured BEFORE save
     ├── post_state captured AFTER save
     └── create_audit_entry() called
              │
              ▼
         Event row created with:
              - actor from auditing context
              - ip_address, user_agent, request_id from context
              - checksum computed (integrity chain)
              - backends_pending populated
              │
              └── transaction.on_commit:
                      _dispatch_event() → file / redis / kafka backends
```

### Authorization Data Flow

```
request.user = Principal (from DualAuthentication)
resource = loaded from DB
action = "update"
     │
     ▼
AuthorizationChecker.check(principal, action, resource)
     │
     ├── 1. DENY policies evaluated
     │      Policy.objects.enabled().filter(effect="deny")
     │          .for_resource(resource).for_action(action).by_priority()
     │      │
     │      └── DSL Evaluator:
     │               context = {principal, resource, action, environment}
     │               ast = Parser().parse(policy.condition)
     │               result = Evaluator().evaluate(ast, context)
     │               if True → DENY immediately
     │
     ├── 2. RBAC assignments checked
     │      RoleAssignment.objects.active()
     │          .for_principal(principal).for_resource(resource)
     │      │
     │      └── For each assignment:
     │               perm_ids = role.get_all_permission_ids()  (includes ancestors)
     │               Permission.objects.filter(pk__in=perm_ids, action=action)
     │               if exists → ALLOW
     │
     ├── 3. ALLOW policies evaluated
     │      (same as DENY but effect="allow")
     │
     └── 4. Default → DENY

AuthzDecision returned:
     .allowed: bool
     .reason: str
     .evaluation_time_ms: float
```

---

## Configuration Reference (All Apps)

```python
# config/settings/base.py

AUTH_USER_MODEL = "accounts.Principal"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    # Project apps (order matters for migrations)
    "apps.core",
    "apps.accounts",
    "apps.authn",
    "apps.sessions",
    "apps.authz",
    "apps.auditing",
]

# ── DRF ──────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.sessions.authentication.DualAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.authn.exception_handler.authn_exception_handler",
}

# ── JWT ──────────────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ── Authentication Backends ───────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    "apps.authn.backends.email.EmailBackend",
    "apps.authn.backends.username.UsernameBackend",
    "apps.authn.backends.phone.PhoneBackend",
    "apps.authn.backends.passwordless.PasswordlessBackend",
]

# ── Core ──────────────────────────────────────────────────────────
CORE_SYSTEM_PRINCIPAL_ID = env("CORE_SYSTEM_PRINCIPAL_ID", default="")
CORE_ENFORCE_ACTOR = False
CORE_DEFAULT_LOCK_DURATION_MINUTES = 30

# ── Accounts ─────────────────────────────────────────────────────
ACCOUNTS = {
    "AUTO_GENERATE_SERVICE_USERNAME": True,
}

# ── Authn ────────────────────────────────────────────────────────
AUTHN = {
    "MAX_FAILED_ATTEMPTS": 5,
    "LOCKOUT_DURATION_MINUTES": 30,
    "PROGRESSIVE_LOCKOUT": True,
    "MFA_ISSUER_NAME": "BBRI",
    "PASSWORD_HISTORY_COUNT": 5,
    "VERIFICATION_TOKEN_TTL_MINUTES": 30,
    "TOKEN_HMAC_KEY": env("TOKEN_HMAC_KEY", default=""),
}

# ── Sessions ─────────────────────────────────────────────────────
SESSION_ENGINE = "apps.sessions.backends.DatabaseSessionBackend"

# ── Authz ────────────────────────────────────────────────────────
# No additional settings required; uses ContentType framework

# ── Auditing ─────────────────────────────────────────────────────
AUDITING = {
    "ENABLED": True,
    "AUDITED_APPS": ["accounts"],
    "BACKENDS": ["file"],
    "BACKEND_OPTIONS": {
        "file": {"path": "logs/audit", "rotate_daily": True},
    },
    "TRACK_DELTAS": True,
    "SNAPSHOT_ON_CREATE": True,
    "SNAPSHOT_INTERVAL": 10,
    "INTEGRITY_ENABLED": True,
    "GLOBAL_EXCLUDE_FIELDS": ["password", "token", "secret", "key"],
}
```

---

## Security Properties Summary

| Property | Implemented by | How |
|---|---|---|
| Session invalidation on password change | `authn` → `accounts` | `principal.bump_security_stamp()` |
| Session invalidation on account lock | `accounts` | `lock()` bumps security stamp |
| HMAC-only token storage | `authn.TokenService` | Only digests stored, not raw values |
| Timing attack prevention | `authn.backends.BaseAccountsBackend` | `_prevent_timing_attack()` |
| Progressive lockout | `authn.LockoutService` | Doubles duration per lockout |
| Immutable audit trail | `auditing` | Append-only + integrity chain |
| Deny-first policy evaluation | `authz.AuthorizationChecker` | DENY policies checked first |
| Password reuse prevention | `authn.PasswordService` | Last N hashes checked |
| No user existence leakage | `authn` reset/passwordless endpoints | Always return 200 |
| Actor attribution on all writes | `core.ActorTrackingMiddleware` | Context variable on every request |

---

## Testing Integration

```python
# conftest.py (project-level)
import pytest
from apps.accounts.services import AccountProvisioner
from apps.sessions.models import AuthSession
from rest_framework.test import APIClient


@pytest.fixture
def provisioner():
    return AccountProvisioner()


@pytest.fixture
def user_principal(provisioner):
    principal, _ = provisioner.provision_user(
        username="testuser",
        password="TestPass123!",
        email="test@example.com",
    )
    return principal


@pytest.fixture
def admin_principal(provisioner):
    principal, _ = provisioner.provision_user(
        username="admin",
        password="AdminPass123!",
        email="admin@example.com",
        is_staff=True,
    )
    return principal


@pytest.fixture
def authenticated_client(user_principal):
    """APIClient authenticated as user_principal."""
    client = APIClient()
    client.force_authenticate(user=user_principal)
    return client


@pytest.fixture
def user_session(user_principal):
    return AuthSession.create_session(
        principal=user_principal,
        channel="api",
        auth_method="password",
        ip_address="127.0.0.1",
    )


# ── Full Integration Test ──────────────────────────────────────────────
@pytest.mark.django_db
def test_full_auth_flow(client):
    """
    Full integration: register → login → access protected resource → logout → audit.
    """
    from apps.accounts.services import AccountProvisioner
    from apps.authz.services import AssignmentService, RoleService
    from apps.auditing.services import get_object_history
    from apps.auditing.enums import EventType

    provisioner = AccountProvisioner()

    # 1. Register
    principal, user = provisioner.provision_user(
        username="integration_test_user",
        password="IntegPass123!",
        email="itest@example.com",
    )
    assert principal.can_authenticate

    # 2. Login via API
    response = client.post("/api/auth/login/", {
        "identifier": "itest@example.com",
        "password": "IntegPass123!",
    })
    assert response.status_code == 200
    access_token = response.data["access"]

    # 3. Access protected endpoint
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    response = client.get("/api/accounts/users/")
    assert response.status_code == 200

    # 4. Logout
    response = client.post("/api/auth/logout/")
    assert response.status_code in (200, 204)

    # 5. Verify audit trail was created
    from apps.auditing.models.event import Event
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(principal.__class__)
    events = Event.objects.filter(content_type=ct, object_id=str(principal.pk))
    assert events.exists()  # at least the CREATE event


@pytest.mark.django_db
def test_security_incident_flow(user_principal, admin_principal):
    """Account lock invalidates sessions; audit trail records the action."""
    from apps.sessions.models import AuthSession
    from apps.auditing.services import get_object_history

    # Create a session
    session = AuthSession.create_session(
        principal=user_principal,
        channel="api",
        auth_method="password",
        ip_address="127.0.0.1",
    )
    stamp_before = user_principal.security_stamp

    # Lock account
    user_principal.lock(
        actor=admin_principal,
        reason="Suspicious activity detected",
    )
    user_principal.refresh_from_db()

    # Security stamp was bumped → sessions are stale
    assert user_principal.security_stamp > stamp_before
    assert user_principal.is_locked
    assert not user_principal.can_authenticate

    # Session stamp is now stale
    session.refresh_from_db()
    assert session.security_stamp_at_issue < user_principal.security_stamp
```
