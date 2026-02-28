# `apps/accounts` — Identity & Account Management

The `accounts` app manages every authenticatable identity in the system.  It
defines `Principal` as `AUTH_USER_MODEL` and four concrete account subtypes:
`UserAccount`, `ServiceAccount`, `APIClient`, and `AgentAccount`.  The
`AccountProvisioner` service creates and tears down principal + account pairs
atomically.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                       apps/accounts                            │
│                                                                │
│  models/                                                       │
│    principal.py ─► Principal (AUTH_USER_MODEL)                 │
│    user.py      ─► UserAccount (profile)                       │
│    service_account.py ─► ServiceAccount (M2M)                  │
│    api_client.py    ─► APIClient (app credentials)             │
│    agent.py         ─► AgentAccount (AI/automation)            │
│    managers.py      ─► PrincipalManager                        │
│    querysets.py     ─► PrincipalQuerySet                       │
│                                                                │
│  services/                                                     │
│    provisioning.py ─► AccountProvisioner                       │
│                        provision_user()                        │
│                        provision_service_account()             │
│                        provision_api_client()                  │
│                        provision_agent()                       │
│                        deprovision()                           │
│                                                                │
│  api/                                                          │
│    views/ ─► PrincipalListCreateView, UserAccountListView ...  │
│    serializers/ ─► per-subtype serializers                     │
│    urls.py ─► /api/accounts/                                   │
│                                                                │
│  enums.py     ─► PrincipalKind, PrincipalStatus                │
│  exceptions.py ─► AccountError hierarchy                       │
│  signals.py   ─► account_provisioned, account_deprovisioned    │
└───────────────────────────────────────────────────────────────┘

                              ┌──────────────────────┐
Principal (1) ────────────── (1) UserAccount         │
           └──────────────── (1) ServiceAccount      │
           └──────────────── (1) APIClient           │
           └──────────────── (1) AgentAccount        │
                              └──────────────────────┘

Sessions, authn, and authz always reference Principal, never a subtype.
```

---

## Models

### `Principal` (`AUTH_USER_MODEL`)

The single authenticatable entity for all account kinds.  Extends Django's
`AbstractBaseUser` + `PermissionsMixin` + `EnterpriseModel`.

**Table:** `principals`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField(pk)` | Auto UUID4 |
| `kind` | `CharField(20)` | `user` / `service` / `api_client` / `agent` |
| `username` | `CharField(150, unique)` | `USERNAME_FIELD` — normalized to lowercase |
| `email` | `EmailField(null, unique)` | Optional, unique if present |
| `email_verified_at` | `DateTimeField(null)` | Set when email is confirmed |
| `phone_number` | `CharField(17)` | E.164 format, validated |
| `phone_verified_at` | `DateTimeField(null)` | Set when phone is confirmed |
| `display_name` | `CharField(150)` | UI-only label |
| `external_id` | `CharField(255)` | SSO / IdP identifier |
| `external_provider` | `CharField(50)` | e.g. `"okta"`, `"google"` |
| `passwordless_enabled` | `BooleanField` | Allow magic-link login |
| `security_stamp` | `BigIntegerField` | Increment to invalidate all sessions |
| `is_staff` | `BooleanField` | Django admin access |
| `last_seen_at` | `DateTimeField(null)` | Updated on successful auth |
| `tags` | `JSONField(list)` | Arbitrary string tags |
| `metadata` | `JSONField(dict)` | Arbitrary structured data |
| *(LifecycleMixin)* | — | `is_active`, `locked_*`, `suspended_*`, `disabled_*`, `expires_at` |
| *(BaseActorMixin)* | — | `created_by`, `updated_by` |
| *(TimestampMixin)* | — | `created_at`, `updated_at` |

#### Key properties

```python
principal.can_authenticate  # True if active, not deleted/disabled/locked/suspended/expired
principal.is_user           # kind == "user"
principal.is_service        # kind == "service"
principal.is_api_client     # kind == "api_client"
principal.is_agent          # kind == "agent"
principal.is_email_verified # email present and email_verified_at set
principal.is_phone_verified # phone_number present and phone_verified_at set
```

#### Key methods

```python
# Explicit display name update (avoids signal-based side effects)
principal.set_display_name("Jane Doe")

# Bump security stamp → invalidates ALL sessions for this principal
new_stamp = principal.bump_security_stamp()

# Lifecycle transitions (all bump security_stamp automatically)
principal.lock(actor=admin, reason="Suspicious activity", duration=timedelta(hours=1))
principal.unlock(actor=admin)
principal.suspend(actor=admin, reason="Under review")
principal.unsuspend(actor=admin)
principal.disable(actor=admin, reason="Account closed")
principal.soft_delete(actor=admin)

# Track last login
principal.record_last_login()
```

---

### `UserAccount`

Human-user profile linked to a Principal.  Stores personal data; identity
lives on `Principal`.

**Table:** `user_accounts`

| Field | Type | Notes |
|---|---|---|
| `principal` | `OneToOneField → Principal` | |
| `given_name` | `CharField(64)` | First name |
| `family_name` | `CharField(64)` | Last name |
| `middle_name` | `CharField(64)` | |
| `nickname` | `CharField(64)` | |
| `picture_url` | `URLField` | Profile image URL |
| `gender` | `CharField(50)` | |
| `birth_date` | `DateField(null)` | |
| `website_url` | `URLField` | |
| `bio` | `TextField(max 1000)` | |
| `metadata` | `JSONField(dict)` | |

**Delegating properties** (reads from `principal`):
```python
user.username   # → principal.username
user.email      # → principal.email
user.full_name  # → "given_name family_name"
user.display_name  # → principal.display_name
```

---

### `ServiceAccount`

Machine/service identity for M2M authentication.

**Table:** `service_accounts`

| Field | Type | Notes |
|---|---|---|
| `principal` | `OneToOneField → Principal` | |
| `name` | `CharField(150, unique)` | Human-readable service identifier |
| `service_name` | `CharField(100)` | Logical service name (e.g. `"payment-gateway"`) |
| `description` | `TextField` | |
| `owner` | `FK → Principal(null)` | User principal who owns this service |
| `allowed_scopes` | `JSONField(list)` | OAuth/authz scope strings |
| `metadata` | `JSONField(dict)` | |

---

### `APIClient`

Application credential for third-party integrations.

**Table:** `api_clients`

| Field | Type | Notes |
|---|---|---|
| `principal` | `OneToOneField → Principal` | |
| `name` | `CharField(150, unique)` | Application name |
| `client_id` | `CharField(128, unique)` | OAuth client identifier |
| `description` | `TextField` | |
| `redirect_uris` | `JSONField(list)` | Allowed OAuth redirect URIs |
| `allowed_scopes` | `JSONField(list)` | |
| `owner` | `FK → Principal(null)` | User who registered this client |
| `metadata` | `JSONField(dict)` | |

---

### `AgentAccount`

AI agent / automated workflow identity.

**Table:** `agent_accounts`

| Field | Type | Notes |
|---|---|---|
| `principal` | `OneToOneField → Principal` | |
| `name` | `CharField(150, unique)` | Agent display name |
| `agent_type` | `CharField(50)` | Category (e.g. `"llm"`, `"rpa"`) |
| `description` | `TextField` | |
| `capabilities` | `JSONField(list)` | What this agent can do |
| `owner` | `FK → Principal(null)` | Responsible human principal |
| `metadata` | `JSONField(dict)` | |

---

## Enums

### `PrincipalKind`

```python
from apps.accounts.enums import PrincipalKind

PrincipalKind.USER        # "user"
PrincipalKind.SERVICE     # "service"
PrincipalKind.API_CLIENT  # "api_client"
PrincipalKind.AGENT       # "agent"
```

---

## Services

### `AccountProvisioner`

Atomic provisioning and deprovisioning.  Every method runs inside
`transaction.atomic()`.  Principal is always created first, then the concrete
account.

```python
from apps.accounts.services import AccountProvisioner

provisioner = AccountProvisioner()
```

#### `provision_user`

```python
principal, user = provisioner.provision_user(
    username="jdoe",
    password="Secr3t!Pass",
    email="jdoe@example.com",
    display_name="Jane Doe",
    phone_number="+14155552671",  # optional
    # Extra fields forwarded to Principal.objects.create_user()
    is_staff=False,
    metadata={"department": "engineering"},
)

print(principal.id)       # UUID
print(principal.kind)     # "user"
print(user.principal_id)  # same UUID
```

#### `provision_service_account`

```python
principal, svc = provisioner.provision_service_account(
    service_name="payment-gateway",
    name="Payment Gateway Service",
    description="Handles payment processing",
    allowed_scopes=["payments.read", "payments.write"],
    # username is auto-generated when AUTO_GENERATE_SERVICE_USERNAME=True
)

print(svc.service_name)  # "payment-gateway"
```

#### `provision_api_client`

```python
principal, client = provisioner.provision_api_client(
    name="Mobile App",
    description="iOS/Android client",
    redirect_uris=["myapp://callback"],
    allowed_scopes=["profile", "openid"],
    owner=admin_principal,
)
```

#### `provision_agent`

```python
principal, agent = provisioner.provision_agent(
    name="Document Processor",
    agent_type="document_ai",
    capabilities=["pdf_parse", "ocr"],
    owner=user_principal,
)
```

#### `deprovision`

Soft-deletes both the concrete account and its Principal atomically, bumping
`security_stamp` to invalidate all sessions.

```python
provisioner.deprovision(principal, actor=admin_principal)
# Both principal and linked account are soft-deleted
```

#### `generate_username`

```python
# Service account username: "svc_payment_gateway_a1b2c3d4"
username = provisioner.generate_username(PrincipalKind.SERVICE, "payment-gateway")

# API client: "api_mobile_app_x9y8z7w6"
username = provisioner.generate_username(PrincipalKind.API_CLIENT, "mobile-app")
```

---

## API Endpoints

All endpoints are prefixed with `/api/accounts/`.

### Principals

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | Staff | List all principals |
| `POST` | `/` | Staff | Create a principal (raw — prefer services) |
| `GET` | `/<uuid>/` | Authenticated | Get principal detail |
| `PATCH` | `/<uuid>/` | Staff | Update principal fields |
| `DELETE` | `/<uuid>/` | Staff | Soft-delete principal |

**List request (GET `/api/accounts/`):**
```
GET /api/accounts/?kind=user&page=1&page_size=20
Authorization: Bearer <token>
```

**Response:**
```json
{
  "count": 142,
  "next": "/api/accounts/?page=2",
  "previous": null,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "kind": "user",
      "username": "jdoe",
      "email": "jdoe@example.com",
      "display_name": "Jane Doe",
      "is_active": true,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

### User Accounts

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/users/` | Authenticated | List user accounts |
| `GET` | `/users/<uuid>/` | Authenticated | Get user profile |
| `PATCH` | `/users/<uuid>/` | Owner / Staff | Update profile fields |

**Update profile (PATCH `/api/accounts/users/<uuid>/`):**
```json
{
  "given_name": "Jane",
  "family_name": "Doe",
  "bio": "Senior engineer",
  "website_url": "https://janedoe.dev"
}
```

### Service Accounts

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/service-accounts/` | Authenticated | List service accounts |
| `POST` | `/service-accounts/` | Staff | Create service account |
| `GET` | `/service-accounts/<uuid>/` | Authenticated | Detail |
| `PATCH` | `/service-accounts/<uuid>/` | Staff | Update |
| `DELETE` | `/service-accounts/<uuid>/` | Staff | Deprovision |

**Create (POST `/api/accounts/service-accounts/`):**
```json
{
  "service_name": "email-sender",
  "name": "Email Sending Service",
  "description": "Transactional email delivery",
  "allowed_scopes": ["email.send"]
}
```

### API Clients

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api-clients/` | Authenticated | List API clients |
| `POST` | `/api-clients/` | Staff | Register new client |
| `GET` | `/api-clients/<uuid>/` | Owner / Staff | Detail |
| `PATCH` | `/api-clients/<uuid>/` | Staff | Update |
| `DELETE` | `/api-clients/<uuid>/` | Staff | Revoke |

### Agents

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/agents/` | Authenticated | List agents |
| `POST` | `/agents/` | Staff | Register agent |
| `GET` | `/agents/<uuid>/` | Authenticated | Detail |
| `PATCH` | `/agents/<uuid>/` | Staff | Update |
| `DELETE` | `/agents/<uuid>/` | Staff | Deprovision |

---

## Exception Hierarchy

```
AccountError
├── AccountDisabledError       — operating on a disabled account
├── AccountLockedError         — operating on a locked account
├── AccountSuspendedError      — operating on a suspended account
├── PrincipalNotFoundError     — principal cannot be resolved
├── PrincipalTypeMismatchError — kind doesn't match expected concrete type
├── SecurityStampMismatchError — session stamp doesn't match principal stamp
├── ProvisioningError          — atomic provisioning failed
├── UsernameConflictError      — username already taken
│     .username attribute carries the conflicting value
└── InvalidUsernameError       — username fails format/reserved/length validation
```

```python
from apps.accounts.exceptions import (
    AccountError,
    UsernameConflictError,
    ProvisioningError,
)

try:
    principal, user = provisioner.provision_user(username="jdoe", ...)
except UsernameConflictError as exc:
    print(f"Username '{exc.username}' is already taken")
except ProvisioningError as exc:
    print(f"Provisioning failed: {exc}")
```

---

## Signals

```python
# apps/accounts/signals.py
from django.dispatch import Signal

account_provisioned    = Signal()  # args: principal, account, kind
account_deprovisioned  = Signal()  # args: principal, kind, actor
```

```python
from django.dispatch import receiver
from apps.accounts.signals import account_provisioned

@receiver(account_provisioned)
def on_account_created(sender, principal, account, kind, **kwargs):
    # Send welcome email, create default resources, etc.
    send_welcome_email(principal.email)
```

---

## Configuration

```python
# config/settings/base.py
ACCOUNTS = {
    # Auto-generate username for service/api_client/agent principals
    "AUTO_GENERATE_SERVICE_USERNAME": True,

    # Username prefix constants (see apps/accounts/constants.py)
    # USERNAME_PREFIX_SERVICE   = "svc_"
    # USERNAME_PREFIX_API_CLIENT = "api_"
    # USERNAME_PREFIX_AGENT     = "agt_"
}
```

---

## Testing Examples

```python
import pytest
from apps.accounts.services import AccountProvisioner
from apps.accounts.exceptions import UsernameConflictError


@pytest.mark.django_db
def test_provision_user():
    provisioner = AccountProvisioner()
    principal, user = provisioner.provision_user(
        username="testuser",
        password="TestPass123!",
        email="test@example.com",
        display_name="Test User",
    )

    assert principal.kind == "user"
    assert principal.username == "testuser"
    assert principal.email == "test@example.com"
    assert user.principal == principal
    assert principal.can_authenticate


@pytest.mark.django_db
def test_username_conflict():
    provisioner = AccountProvisioner()
    provisioner.provision_user(username="alice", password="Pass123!")

    with pytest.raises(UsernameConflictError) as exc_info:
        provisioner.provision_user(username="alice", password="Other123!")

    assert exc_info.value.username == "alice"


@pytest.mark.django_db
def test_deprovision(user_principal):
    provisioner = AccountProvisioner()
    provisioner.deprovision(user_principal, actor=user_principal)

    user_principal.refresh_from_db()
    assert user_principal.is_deleted
    assert user_principal.can_authenticate is False


@pytest.mark.django_db
def test_lifecycle_operations(user_principal, admin_principal):
    from datetime import timedelta

    # Lock
    user_principal.lock(
        actor=admin_principal,
        reason="Suspicious login",
        duration=timedelta(minutes=30),
    )
    assert user_principal.is_locked
    assert not user_principal.can_authenticate

    # Unlock
    user_principal.unlock(actor=admin_principal)
    assert not user_principal.is_locked
    assert user_principal.can_authenticate
```
