# `apps/sessions` — Session Management

Enterprise session management built on a state-machine `AuthSession` model.
Supports dual authentication (JWT tokens + cookie-based sessions), multi-device
tracking, risk-based controls, and full lifecycle management (lock, revoke,
expire, logout).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      apps/sessions                            │
│                                                               │
│  models/                                                      │
│    auth_session.py  AuthSession (state machine)               │
│    credentials.py   SessionCredential (hashed cookie/token)   │
│    managers.py      AuthSessionManager                        │
│    querysets.py     AuthSessionQuerySet                       │
│                                                               │
│  services/                                                    │
│    lifecycle.py     revoke_session, logout_session, ...       │
│    device.py        Device fingerprinting helpers             │
│    risk.py          Risk scoring for sessions                 │
│                                                               │
│  authentication.py  CookieJWTAuthentication                   │
│                     SessionAuthentication                     │
│                     DualAuthentication                        │
│                                                               │
│  backends.py        DatabaseSessionBackend                    │
│  middleware.py      SessionTrackingMiddleware                 │
│                                                               │
│  api/                                                         │
│    views.py    SessionListView, SessionTerminateView          │
│    urls.py     /api/sessions/                                 │
│                                                               │
│  enums.py      SessionChannel                                 │
└──────────────────────────────────────────────────────────────┘

                 ┌──────────────────────────────────┐
                 │         Session State Machine     │
                 │                                   │
                 │  ACTIVE ──► LOCKED ──► ACTIVE     │
                 │    │                              │
                 │    ├──► SUSPENDED ──► ACTIVE      │
                 │    │                              │
                 │    ├──► DISABLED (revoked)        │
                 │    │                              │
                 │    └──► logged_out_at set         │
                 │          (non-terminal, resumable)│
                 └──────────────────────────────────┘
```

---

## Models

### `AuthSession`

The canonical session record for all principal types (user, service, API client).

**Table:** `auth_sessions`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField(pk)` | Session identifier |
| `principal` | `FK → Principal` | Who owns this session |
| `authenticated_at` | `DateTimeField(null)` | When authentication completed |
| `last_seen_at` | `DateTimeField(null)` | Last observed activity (updated by middleware) |
| `idle_expires_at` | `DateTimeField(null)` | Idle TTL expiry |
| `revoked_at` | `DateTimeField(null)` | When admin force-terminated |
| `logged_out_at` | `DateTimeField(null)` | When user voluntarily logged out (non-terminal) |
| `user_agent` | `CharField(500)` | Browser/client user agent string |
| `ip_first` | `GenericIPAddressField(null)` | IP at session creation |
| `ip_last` | `GenericIPAddressField(null)` | Most recent IP |
| `device_id` | `CharField(128)` | Device identifier |
| `device_fingerprint` | `CharField(255)` | Fingerprint hash |
| `is_trusted_device` | `BooleanField` | Trusted device flag |
| `scopes` | `JSONField(list)` | OAuth/auth scopes |
| `metadata` | `JSONField(dict)` | Flexible metadata (channel, auth_method, etc.) |
| `security_stamp_at_issue` | `BigIntegerField` | Principal stamp when session was created |
| *(LifecycleMixin)* | — | `is_active`, `locked_*`, `suspended_*`, `disabled_*`, `expires_at` |

**Metadata sub-fields** (stored in `metadata` JSON):

| Key | Values | Description |
|---|---|---|
| `channel` | `browser` / `api` / `service` / `agent` | Session channel |
| `auth_method` | `password` / `totp` / `webauthn` / `passwordless` | Authentication method |
| `auth_status` | `authenticated` / `pending_mfa` | Current auth state |
| `mfa_method` | `totp` / `backup_code` / `none` | MFA method used |
| `device_type` | `desktop` / `mobile` / `tablet` | Device classification |

**Properties:**
```python
session.expired         # is_expired from LifecycleMixin
session.idle_expired    # idle_expires_at < now
session.locked          # is_locked from LifecycleMixin

session.channel         # metadata["channel"]
session.auth_method     # metadata["auth_method"]
session.auth_status     # metadata["auth_status"]
session.device_type     # metadata["device_type"]
session.ip_address      # most recent IP (ip_last or ip_first)
session.last_activity_at  # last_seen_at alias
```

#### Validity check

A session is **valid** when ALL of the following hold:
1. `status = ACTIVE`
2. `metadata["auth_status"] = authenticated`
3. Not expired (absolute or idle TTL)
4. Not locked (`locked_until` null or in the past)
5. Principal is active and `security_stamp_at_issue == principal.security_stamp`

---

### `SessionCredential`

Stores hashed cookie handles and refresh tokens — raw values are never persisted.

| Field | Type | Notes |
|---|---|---|
| `session` | `FK → AuthSession` | |
| `credential_type` | `CharField` | `cookie_handle` / `refresh_token` |
| `credential_hash` | `CharField` | HMAC-SHA256 hash |
| `expires_at` | `DateTimeField(null)` | |
| `used_at` | `DateTimeField(null)` | For single-use credentials |

---

## `AuthSessionManager` — Creating Sessions

```python
from apps.sessions.models import AuthSession
from apps.sessions.models.enums import SessionChannel
from apps.authn.models.enums import AuthenticationStatus, MFAMethod

# Full manager API
session, cookie_handle_raw, refresh_token_raw = AuthSession.objects.create_session(
    principal=principal,
    channel=SessionChannel.BROWSER,
    auth_method="password",
    auth_status=AuthenticationStatus.AUTHENTICATED,
    mfa_method=MFAMethod.NONE,
    user_agent="Mozilla/5.0 ...",
    ip_address="203.0.113.42",
    absolute_ttl=timedelta(hours=8),  # None → uses settings
)
# cookie_handle_raw / refresh_token_raw: str — send to client, store hashes internally

# Compatibility wrapper (returns session only, no raw credentials)
session = AuthSession.create_session(
    principal=principal,
    channel="api",
    auth_method="password",
    expires_in=timedelta(hours=24),
    user_agent="MyApp/1.0",
    ip_address="203.0.113.42",
    require_mfa=False,
)
```

---

## Session Lifecycle Operations

```python
# Revoke (admin force-terminate, terminal)
session.revoke(reason="Suspicious activity", revoked_by=admin)
print(session.revoked_at)    # datetime

# Logout (user-initiated, non-terminal — can re-authenticate)
session.logout(reason="User logged out")
print(session.logged_out_at) # datetime
print(session.status)        # still ACTIVE

# Lock (temporary security enforcement)
session.lock(duration=timedelta(minutes=30), reason="IP anomaly")
print(session.is_locked)     # True

# Unlock
session.unlock()

# Mark expired
session.mark_expired(reason="TTL exceeded")

# Extend expiry
session.extend_expiry(duration=timedelta(hours=12))

# Touch activity (updates last_seen_at + idle_expires_at)
session.touch_activity(ip_address="203.0.113.42", path="/api/projects/")
```

---

## Bulk / Helper Operations

```python
# Get all active sessions for a principal
active = AuthSession.get_active_for_principal(user)

# Terminate all sessions for a principal (except optionally one)
terminated_count = AuthSession.terminate_all_for_principal(
    user,
    except_session=current_session,
    reason="Password changed",
    actor=user,
)

# Cleanup old terminal sessions
cleaned = AuthSession.cleanup_expired_sessions(older_than_days=30)
```

---

## QuerySet API

```python
from apps.sessions.models import AuthSession

# Filters
AuthSession.objects.for_principal(principal)
AuthSession.objects.active()          # not deleted/disabled/suspended
AuthSession.objects.expired()         # expires_at < now
AuthSession.objects.by_channel("browser")
AuthSession.objects.by_device(device_fingerprint="abc123")
```

---

## Services

### `lifecycle.py`

```python
from apps.sessions.services.lifecycle import (
    revoke_session,
    revoke_all_user_sessions,
    logout_session,
    expire_session,
    cleanup_expired_sessions,
    extend_session_expiry,
)

# Revoke one session
revoke_session(session, reason="Suspicious activity", actor=admin)

# Revoke all for a user (except current)
count = revoke_all_user_sessions(
    user,
    except_session=current_session,
    reason="Security incident",
    actor=admin,
)

# Non-terminal logout
logout_session(session, reason="User logged out")

# Cleanup old terminal sessions
count = cleanup_expired_sessions(older_than_days=30)
```

### `risk.py`

Risk scoring for sessions (used internally by middleware and login flows).

```python
from apps.sessions.services.risk import calculate_risk_score

score = calculate_risk_score(
    session=session,
    request=request,
)
# score: float 0.0–1.0; higher = higher risk
# Considers: IP change, device fingerprint change, activity patterns
```

### `device.py`

Device fingerprinting.

```python
from apps.sessions.services.device import generate_device_fingerprint, classify_device

fingerprint = generate_device_fingerprint(
    user_agent="Mozilla/5.0 ...",
    ip_address="203.0.113.42",
    accept_language="en-US",
)

device_type = classify_device(user_agent="Mozilla/5.0 (iPhone; ...)")
# "mobile"
```

---

## Authentication Classes (DRF)

Configure in `REST_FRAMEWORK`:

```python
# config/settings/base.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.sessions.authentication.DualAuthentication",
    ],
}
```

| Class | Accepts | Notes |
|---|---|---|
| `CookieJWTAuthentication` | JWT from `Authorization` header or `access` cookie | Validates JWT, loads session |
| `SessionAuthentication` | Django session cookie (`session_id`) | Loads `AuthSession` |
| `DualAuthentication` | JWT or session cookie | Tries JWT first, falls back to session |

```python
# In a view, access the session via request.user_session
class MyView(APIView):
    def get(self, request):
        session = request.user_session
        print(session.channel)   # "api" / "browser" / etc.
        print(session.ip_last)
```

---

## Middleware

### `SessionTrackingMiddleware`

Updates `last_seen_at` (and `idle_expires_at`) on every authenticated request.
Also attaches `request.user_session`.

```python
# config/settings/base.py
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.sessions.middleware.SessionTrackingMiddleware",  # after AuthenticationMiddleware
    "apps.core.middleware.ActorTrackingMiddleware",
]
```

---

## Session Backend

Replace Django's default session backend with `AuthSession`-backed storage:

```python
# config/settings/base.py
SESSION_ENGINE = "apps.sessions.backends.DatabaseSessionBackend"
```

---

## API Endpoints

All endpoints are prefixed with `/api/sessions/`.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | Required | List all active sessions |
| `DELETE` | `/all/` | Required | Terminate all OTHER sessions |
| `DELETE` | `/<uuid>/` | Required | Terminate a specific session |

**List sessions (GET `/api/sessions/`):**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "ip_address": "203.0.113.42",
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
    "device_type": "desktop",
    "device_name": "MacBook Pro",
    "location_city": "New York",
    "location_country": "US",
    "created_at": "2024-01-15T09:00:00Z",
    "last_activity_at": "2024-01-15T10:30:00Z",
    "expires_at": "2024-01-16T09:00:00Z",
    "is_current": true
  }
]
```

**Terminate all others (DELETE `/api/sessions/all/`):**
```json
// Response (200)
{ "message": "Terminated 3 sessions." }
```

**Terminate specific session (DELETE `/api/sessions/<uuid>/`):**
```json
// Response (204 No Content)
```

---

## Enums

### `SessionChannel`

```python
from apps.sessions.enums import SessionChannel

SessionChannel.BROWSER  # "browser"
SessionChannel.API      # "api"
SessionChannel.SERVICE  # "service"
SessionChannel.AGENT    # "agent"
```

---

## Compliance

| Standard | Requirement | Implementation |
|---|---|---|
| ISO 27001 A.9.4 | Session management | `AuthSession` state machine |
| SOC 2 CC6.3 | Logical and physical access | Lock/suspend/revoke controls |
| NIST 800-63B | Digital authentication | Session binding to security stamp |
| OWASP Session Mgmt | Best practices | Hashed credentials, idle TTL |
| PSD2 | Strong customer authentication | MFA pending state tracking |

---

## Configuration

Session TTLs and behavior are configured via `SIMPLE_JWT` + session-specific settings:

```python
# config/settings/base.py
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SESSIONS = {
    "ABSOLUTE_TTL": timedelta(hours=8),      # Max session duration
    "IDLE_TTL": timedelta(hours=2),          # Inactivity expiry
    "CLEANUP_DAYS": 30,                      # Days before terminal sessions are purged
    "TRACK_ACTIVITY": True,                  # Update last_seen_at on every request
}
```

---

## Testing Examples

```python
import pytest
from datetime import timedelta
from apps.sessions.models import AuthSession
from apps.sessions.enums import SessionChannel


@pytest.mark.django_db
def test_create_session(user_principal):
    session = AuthSession.create_session(
        principal=user_principal,
        channel="api",
        auth_method="password",
        ip_address="127.0.0.1",
        user_agent="pytest/1.0",
    )
    assert session.principal == user_principal
    assert not session.expired
    assert not session.is_locked


@pytest.mark.django_db
def test_revoke_session(user_principal):
    session = AuthSession.create_session(
        principal=user_principal,
        channel="api",
        auth_method="password",
        ip_address="127.0.0.1",
    )
    session.revoke(reason="Test revocation")
    session.refresh_from_db()
    assert session.revoked_at is not None
    assert session.is_disabled


@pytest.mark.django_db
def test_security_stamp_invalidation(user_principal):
    session = AuthSession.create_session(
        principal=user_principal,
        channel="api",
        auth_method="password",
        ip_address="127.0.0.1",
    )
    stamp_before = session.security_stamp_at_issue

    # Bump stamp (e.g., password change)
    user_principal.bump_security_stamp()

    # Session stamp is now stale
    assert session.security_stamp_at_issue != user_principal.security_stamp


@pytest.mark.django_db
def test_terminate_all_sessions(user_principal):
    # Create 3 sessions
    sessions = [
        AuthSession.create_session(
            principal=user_principal,
            channel="api",
            auth_method="password",
            ip_address="127.0.0.1",
        )
        for _ in range(3)
    ]

    # Terminate all except the first
    count = AuthSession.terminate_all_for_principal(
        user_principal,
        except_session=sessions[0],
    )
    assert count == 2
```
