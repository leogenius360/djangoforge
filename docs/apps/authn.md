# `apps/authn` — Authentication

Enterprise-grade authentication subsystem.  Handles password login, MFA
(TOTP + backup codes), passwordless authentication, password management,
email/phone verification, and account lockout.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       apps/authn                             │
│                                                              │
│  api/views/                                                  │
│    auth.py         LoginView, MFALoginView, LogoutView        │
│    mfa.py          MFAStatusView, MFASetupView, ...           │
│    password.py     PasswordChangeView, PasswordResetView, ... │
│    passwordless.py PasswordlessRequestView, ...               │
│    verification.py EmailVerification*, PhoneVerification*     │
│                                          ▲                   │
│                                          │ thin HTTP wrappers │
│  services/                               │                   │
│    authentication.py  AuthenticationService (orchestrator)   │
│    mfa.py             MFAService                             │
│    password.py        PasswordService                        │
│    lockout.py         LockoutService                         │
│    token.py           TokenService (HMAC tokens/OTPs)        │
│    verification.py    VerificationService                    │
│                                          │                   │
│  models/                                 │                   │
│    credentials.py  PasswordCredential, TOTPCredential, ...   │
│    challenges.py   VerificationToken                         │
│    login_attempts.py  LoginAttempt                           │
│    mfa_pending.py  MFAPendingAuthentication                  │
│    password_history.py  PasswordHistory                      │
│                                                              │
│  backends/                                                   │
│    email.py / username.py / phone.py / passwordless.py       │
│    (credential verification only — no session creation)      │
│                                                              │
│  signals.py    18 lifecycle signals                          │
│  exceptions.py Full exception hierarchy                      │
└─────────────────────────────────────────────────────────────┘
```

**Key design principles:**
- **Service-first** — views are thin HTTP wrappers; all logic lives in services.
- **HMAC-only storage** — raw tokens and OTP codes are never stored; only HMAC-SHA256 digests.
- **Backends verify only** — Django auth backends do not create sessions.
- **Signal-driven extensibility** — 18 signals cover the full auth lifecycle.

---

## Models

### `PasswordCredential`

Stores the credential status for password-based auth (the actual password hash
is on `Principal.password` via Django's `AbstractBaseUser`).

| Field | Type | Notes |
|---|---|---|
| `principal` | `FK → Principal` | |
| `status` | `CharField` | `active` / `inactive` / `revoked` |
| `last_changed_at` | `DateTimeField(null)` | |
| `expires_at` | `DateTimeField(null)` | Enforced by `PasswordService` |

### `TOTPCredential`

TOTP secret for MFA.

| Field | Type | Notes |
|---|---|---|
| `principal` | `FK → Principal` | |
| `secret` | `CharField` | Base32-encoded TOTP secret |
| `label` | `CharField` | Issuer label (from `MFA_ISSUER_NAME` setting) |
| `algorithm` | `CharField` | Default `SHA1` |
| `digits` | `IntegerField` | Default `6` |
| `period` | `IntegerField` | Default `30` seconds |
| `status` | `CharField` | `active` / `inactive` (inactive = setup pending) |

### `BackupCode`

Hashed one-time backup codes for MFA recovery.

| Field | Type | Notes |
|---|---|---|
| `principal` | `FK → Principal` | |
| `code_hash` | `CharField` | `make_password(code)` |
| `used_at` | `DateTimeField(null)` | Set when consumed |

### `VerificationToken`

HMAC-based token for email/phone verification, password reset, and passwordless
login.

| Field | Type | Notes |
|---|---|---|
| `principal` | `FK → Principal` | |
| `purpose` | `CharField` | `email_verification` / `phone_verification` / `password_reset` / `passwordless` |
| `token_hash` | `CharField` | HMAC-SHA256 of the raw token |
| `expires_at` | `DateTimeField` | Controlled by purpose-specific TTL settings |
| `used_at` | `DateTimeField(null)` | Set when consumed |
| `attempt_count` | `PositiveIntegerField` | Incremented on each verification attempt |
| `max_attempts` | `PositiveIntegerField` | Permanent invalidation after exceeding |

### `LoginAttempt`

Tracks failed login attempts for lockout enforcement.

| Field | Type | Notes |
|---|---|---|
| `principal` | `FK → Principal(null)` | Null when user not found |
| `identifier` | `CharField` | Login identifier used (email/username/phone) |
| `ip_address` | `GenericIPAddressField(null)` | |
| `user_agent` | `CharField` | |
| `result` | `CharField` | `success` / `failure` / `account_locked` / `account_disabled` |
| `reason` | `CharField` | e.g. `"invalid_credentials"` |
| `auth_method` | `CharField` | `password` / `totp` / `passwordless` / etc. |

### `MFAPendingAuthentication`

DB-backed MFA state between password success and TOTP verification.

| Field | Type | Notes |
|---|---|---|
| `principal` | `FK → Principal` | |
| `token_hash` | `CharField` | HMAC-SHA256 of the raw MFA token |
| `auth_method` | `CharField` | Method used to pass the first factor |
| `expires_at` | `DateTimeField` | Controlled by `MFA_PENDING_TTL_MINUTES` |
| `attempt_count` | `PositiveIntegerField` | Fails permanently after `MFA_PENDING_MAX_ATTEMPTS` |
| `completed_at` | `DateTimeField(null)` | Set when second factor is verified |

### `PasswordHistory`

Password reuse prevention.

| Field | Type | Notes |
|---|---|---|
| `principal` | `FK → Principal` | |
| `password_hash` | `CharField` | Hashed previous password |
| `created_at` | `DateTimeField` | |

---

## Services

### `AuthenticationService`

Central orchestrator for all authentication flows.

#### `authenticate_with_password`

```python
from apps.authn.services.authentication import AuthenticationService

try:
    result = AuthenticationService.authenticate_with_password(
        request=request,
        identifier="jdoe@example.com",  # email or username
        password="Secr3t!Pass",
    )
    # result.principal   — authenticated Principal
    # result.session     — created AuthSession
    # result.auth_method — "password"
    # result.access_token, result.refresh_token, result.expires_in
    # result.mfa_method  — MFAMethod.NONE if no MFA

except MFARequiredError as exc:
    # First factor passed; second factor needed
    print(exc.mfa_token)  # short-lived token to present to /login/mfa/

except AccountLockedError:
    # Account is locked out
    ...

except InvalidCredentialsError:
    # Bad credentials
    ...
```

#### `authenticate_mfa`

```python
from apps.authn.services.authentication import AuthenticationService

result = AuthenticationService.authenticate_mfa(
    request=request,
    mfa_token="<token from MFARequiredError>",
    code="123456",  # TOTP code or backup code
)
```

#### `authenticate_passwordless`

```python
result = AuthenticationService.authenticate_passwordless(
    request=request,
    identifier="jdoe@example.com",
    token="<magic-link token>",
)
```

#### `logout`

```python
# Terminate current session
AuthenticationService.logout(request=request, session=current_session)

# Terminate ALL sessions for the user
AuthenticationService.logout(request=request, session=current_session, all_sessions=True)
```

---

### `MFAService`

TOTP and backup code management.

#### Setup flow

```python
from apps.authn.services.mfa import MFAService

# Step 1: Initiate setup
setup = MFAService.setup_totp(principal)
# Returns: {"secret": "BASE32SECRET", "provisioning_uri": "otpauth://...", "credential_id": "..."}

# User scans QR code from provisioning_uri in their authenticator app

# Step 2: Activate by verifying first code
result = MFAService.activate_totp(principal, code="123456")
# Returns: {"backup_codes": ["code1", "code2", ..., "code10"]}
# ↑ Store backup codes securely — shown only once!
```

#### Verification during login

```python
from apps.authn.services.mfa import MFAService, MFAVerificationResult

# Verify TOTP code
result: MFAVerificationResult = MFAService.verify_code(principal, code="123456")
# result.valid: bool
# result.method: "totp" | "backup_code" | None

# Verify backup code
result = MFAService.verify_code(principal, code="ABCD-EFGH")
```

#### Management

```python
# Check status
status = MFAService.get_status(principal)
# Returns: {"enabled": True, "has_backup_codes": True, "backup_codes_remaining": 7}

# Disable MFA (bumps security_stamp → invalidates sessions)
MFAService.disable_mfa(principal, actor=admin)

# Regenerate backup codes
new_codes = MFAService.regenerate_backup_codes(principal)
# Returns: ["code1", ..., "code10"]
```

---

### `PasswordService`

Password lifecycle management.

```python
from apps.authn.services.password import PasswordService

# Change password (validates current, enforces history, bumps security_stamp)
PasswordService.change_password(
    principal=principal,
    current_password="OldPass123!",
    new_password="NewPass456!",
    request=request,
)

# Request password reset (always succeeds, never leaks user existence)
PasswordService.request_reset(
    identifier="jdoe@example.com",
    request=request,
)
# token is sent to user's email out-of-band

# Confirm password reset
PasswordService.confirm_reset(
    token="<reset-token>",
    new_password="FreshPass789!",
)

# Check if password is expired
is_expired = PasswordService.is_password_expired(principal)
```

---

### `LockoutService`

Progressive brute-force protection.

```python
from apps.authn.services.lockout import LockoutService

# Check lockout status (raises AccountLockedError if locked)
LockoutService.check_lockout(principal)

# Record a failed attempt (may lock the account)
LockoutService.record_failure(principal, request=request, identifier="jdoe@example.com")

# Reset failed attempts on success
LockoutService.reset_attempts(principal)

# Manual unlock
LockoutService.unlock_account(principal, actor=admin)
```

---

### `TokenService`

HMAC-based token creation and verification.

```python
from apps.authn.services.token import TokenService
from apps.authn.models import TokenPurpose

# Create a token for email verification
raw_token, token_obj = TokenService.create_token(
    principal=principal,
    purpose=TokenPurpose.EMAIL_VERIFICATION,
)
# raw_token: str — the value to send to user
# token_obj: VerificationToken — DB record (stores HMAC digest only)

# Verify a token (increments attempt_count, raises on failure)
token_obj = TokenService.verify_token(
    principal=principal,
    purpose=TokenPurpose.EMAIL_VERIFICATION,
    token=raw_token,
)

# Consume (verify + mark used)
token_obj = TokenService.consume_token(
    principal=principal,
    purpose=TokenPurpose.EMAIL_VERIFICATION,
    token=raw_token,
)
```

---

### `VerificationService`

Email and phone verification workflows.

```python
from apps.authn.services.verification import VerificationService

# Request email verification (sends token to user email)
VerificationService.request_email_verification(principal, request=request)

# Confirm email with token
VerificationService.confirm_email_verification(principal, token="<verification-token>")
# Sets principal.email_verified_at

# Request phone OTP
VerificationService.request_phone_verification(principal, request=request)

# Confirm phone OTP
VerificationService.confirm_phone_verification(principal, otp="123456")
# Sets principal.phone_verified_at
```

---

## API Endpoints

All endpoints are prefixed with `/api/auth/`.

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/login/` | None | Password login |
| `POST` | `/login/mfa/` | None | Complete MFA step |
| `POST` | `/logout/` | Required | End session(s) |
| `POST` | `/token/refresh/` | None | Refresh JWT |
| `POST` | `/token/verify/` | None | Verify JWT |

**Login (POST `/api/auth/login/`):**
```json
// Request
{
  "identifier": "jdoe@example.com",
  "password": "Secr3t!Pass"
}

// Success response (200)
{
  "access": "eyJhbGci...",
  "refresh": "eyJhbGci...",
  "expires_in": 3600,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}

// MFA required (200 — not 401, client must redirect to MFA step)
{
  "mfa_required": true,
  "mfa_token": "abc123def456",
  "message": "Multi-factor authentication required."
}
```

**MFA Login (POST `/api/auth/login/mfa/`):**
```json
// Request
{
  "mfa_token": "abc123def456",
  "code": "123456"
}

// Success (200) — same as login response
{
  "access": "eyJhbGci...",
  "refresh": "eyJhbGci...",
  "expires_in": 3600
}
```

**Logout (POST `/api/auth/logout/`):**
```json
// Request (terminate all sessions)
{ "all_sessions": true }

// Response (204 No Content)
```

### Password Management

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/password/change/` | Required | Change password |
| `POST` | `/password/reset/` | None | Request reset (always 200) |
| `POST` | `/password/reset/confirm/` | None | Confirm reset |

**Change password (POST `/api/auth/password/change/`):**
```json
// Request
{
  "current_password": "OldPass123!",
  "new_password": "NewPass456!",
  "confirm_password": "NewPass456!"
}
// Response (200)
{ "message": "Password changed successfully." }
```

**Reset request (POST `/api/auth/password/reset/`):**
```json
// Request
{ "email": "jdoe@example.com" }
// Always returns 200 regardless of whether email exists
{ "message": "If an account exists, a reset link has been sent." }
```

**Reset confirm (POST `/api/auth/password/reset/confirm/`):**
```json
// Request
{
  "token": "<reset-token>",
  "new_password": "FreshPass789!",
  "confirm_password": "FreshPass789!"
}
// Response (200)
{ "message": "Password reset successfully." }
```

### MFA Management

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/mfa/status/` | Required | Get MFA status |
| `POST` | `/mfa/setup/` | Required | Initiate TOTP setup |
| `POST` | `/mfa/setup/` (activate) | Required | Activate TOTP |
| `POST` | `/mfa/disable/` | Required | Disable MFA |
| `POST` | `/mfa/backup-codes/` | Required | Regenerate backup codes |

**MFA status (GET `/api/auth/mfa/status/`):**
```json
{
  "enabled": true,
  "has_backup_codes": true,
  "backup_codes_remaining": 7
}
```

**MFA setup (POST `/api/auth/mfa/setup/`):**
```json
// Request (start setup)
{ "action": "initiate" }
// Response
{
  "secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/BBRI:jdoe%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=BBRI",
  "credential_id": "550e8400-e29b-41d4-a716-446655440000"
}

// Request (activate with first code)
{ "action": "activate", "code": "123456" }
// Response
{
  "backup_codes": [
    "ABCD-EFGH", "IJKL-MNOP", "QRST-UVWX",
    "YZAB-CDEF", "GHIJ-KLMN", "OPQR-STUV",
    "WXYZ-ABCD", "EFGH-IJKL", "MNOP-QRST",
    "UVWX-YZAB"
  ]
}
```

### Passwordless Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/passwordless/request/` | None | Send magic link / OTP |
| `POST` | `/passwordless/verify/` | None | Verify token/OTP |
| `POST` | `/passwordless/totp/` | None | TOTP-based passwordless |

**Request (POST `/api/auth/passwordless/request/`):**
```json
// Request
{ "identifier": "jdoe@example.com" }
// Response (200 — always, no user existence leak)
{ "message": "If passwordless is enabled, a login link has been sent." }
```

**Verify (POST `/api/auth/passwordless/verify/`):**
```json
// Request
{ "identifier": "jdoe@example.com", "token": "<otp-or-token>" }
// Success response — same as login
{ "access": "eyJhbGci...", "refresh": "eyJhbGci..." }
```

### Verification

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/verify/email/request/` | Required | Request email verification |
| `POST` | `/verify/email/confirm/` | None | Confirm email token |
| `POST` | `/verify/phone/request/` | Required | Request phone OTP |
| `POST` | `/verify/phone/confirm/` | Required | Confirm phone OTP |

**Email verify confirm (POST `/api/auth/verify/email/confirm/`):**
```json
{ "token": "<email-verification-token>" }
// Response (200)
{ "message": "Email verified successfully." }
```

---

## Exception Hierarchy

All exceptions inherit from `AuthenticationError`.

```
AuthenticationError (401)
├── InvalidCredentialsError (401)       "Invalid credentials."
├── CredentialExpiredError (401)         "Credentials have expired."
├── PasswordReuseError (400)            "Cannot reuse a recent password."
├── PasswordValidationError (400)       "Password does not meet requirements."
├── AccountLockedError (423)            "Account is temporarily locked."
├── AccountDisabledError (403)          "Account has been disabled."
├── MFARequiredError (401)              "Multi-factor authentication required."
│     .mfa_token attribute — present the token to /login/mfa/
├── MFAVerificationFailedError (401)    "MFA verification failed."
├── MFAPendingExpiredError (401)        "MFA session has expired."
├── MFAAlreadyEnabledError (409)        "MFA is already enabled."
├── MFANotEnabledError (409)            "MFA is not enabled."
├── VerificationTokenError (400)
│   ├── TokenInvalidError (400)         "Invalid or expired token."
│   ├── TokenExpiredError (400)         "Token has expired."
│   ├── TokenAlreadyUsedError (400)     "Token has already been used."
│   └── OTPAttemptsExceededError (429)  "Too many attempts."
├── RateLimitExceededError (429)        "Too many requests."
├── PasswordlessNotEnabledError (400)   "Passwordless login is not enabled."
└── CooldownActiveError (429)           "Please wait before requesting again."
```

**HTTP error response format:**
```json
{
  "error": "InvalidCredentialsError",
  "detail": "Invalid credentials.",
  "status_code": 401
}
```

---

## Signals

18 signals cover the full authentication lifecycle, all connected in `apps.py` via `connect_signals()`.

| Signal | Args | Emitted when |
|---|---|---|
| `login_succeeded` | `user, request, auth_method, session` | Successful login |
| `login_failed` | `identifier, request, reason, user` | Failed login attempt |
| `logout_completed` | `user, request, all_sessions` | User logs out |
| `mfa_challenge_issued` | `user, request` | MFA challenge sent |
| `mfa_verified` | `user, request, method` | MFA successfully verified |
| `mfa_failed` | `user, request` | MFA verification failed |
| `mfa_enabled` | `user, request` | MFA activated |
| `mfa_disabled` | `user, request` | MFA disabled |
| `credential_created` | `user, credential, credential_type` | New credential created |
| `credential_revoked` | `user, credential, credential_type` | Credential revoked |
| `password_changed` | `user, request` | Password changed |
| `password_reset_requested` | `user, token_id` | Password reset requested |
| `account_locked` | `user, locked_until, attempt_count` | Account locked out |
| `account_unlocked` | `user` | Account unlocked |
| `verification_token_created` | `user, purpose, token_id` | Token created |
| `verification_token_used` | `user, purpose, token_id` | Token consumed |
| `email_verification_confirmed` | `user` | Email verified |
| `phone_verification_confirmed` | `user` | Phone verified |

```python
from django.dispatch import receiver
from apps.authn.signals import login_failed, account_locked

@receiver(login_failed)
def on_login_failed(sender, identifier, request, reason, user=None, **kwargs):
    # Alert security team, log to SIEM, etc.
    logger.warning("Login failed for %s: %s", identifier, reason)

@receiver(account_locked)
def on_account_locked(sender, user, locked_until, attempt_count, **kwargs):
    send_security_alert(user.email, locked_until=locked_until)
```

---

## Authentication Backends

Configured in `AUTHENTICATION_BACKENDS`:

| Backend | Lookup | Notes |
|---|---|---|
| `EmailBackend` | `email` (case-insensitive) | Falls back to `username` kwarg |
| `UsernameBackend` | `username` (case-insensitive) | Standard user + password |
| `PhoneBackend` | `phone_number` | Requires `phone_verified_at` to be set |
| `PasswordlessBackend` | token | Delegates to `TokenService.verify_token()` |

All extend `BaseAccountsBackend` which adds:
- `user_can_authenticate()` — checks `is_active` + not locked
- `_prevent_timing_attack()` — runs password hasher even when user not found

---

## Configuration

```python
# config/settings/base.py
AUTHN = {
    # Lockout policy
    "MAX_FAILED_ATTEMPTS": 5,
    "LOCKOUT_DURATION_MINUTES": 30,
    "PROGRESSIVE_LOCKOUT": True,
    "PROGRESSIVE_LOCKOUT_MAX_MINUTES": 1440,  # 24h cap

    # Password policy
    "PASSWORD_HISTORY_COUNT": 5,
    "PASSWORD_MAX_AGE_DAYS": 90,            # None to disable

    # MFA
    "MFA_ISSUER_NAME": "BBRI",
    "MFA_BACKUP_CODE_COUNT": 10,
    "TOTP_VALID_WINDOW": 1,
    "MFA_PENDING_TTL_MINUTES": 5,
    "MFA_PENDING_MAX_ATTEMPTS": 5,

    # Verification tokens
    "VERIFICATION_TOKEN_TTL_MINUTES": 30,
    "EMAIL_VERIFICATION_TOKEN_TTL_MINUTES": 1440,  # 24h
    "EMAIL_VERIFICATION_COOLDOWN_SECONDS": 60,
    "PHONE_VERIFICATION_OTP_TTL_MINUTES": 10,
    "PHONE_VERIFICATION_OTP_LENGTH": 6,
    "PHONE_VERIFICATION_COOLDOWN_SECONDS": 60,
    "PHONE_VERIFICATION_MAX_ATTEMPTS": 5,

    # Passwordless
    "PASSWORDLESS_TOKEN_TTL_MINUTES": 10,
    "PASSWORDLESS_OTP_LENGTH": 6,
    "PASSWORDLESS_OTP_MAX_ATTEMPTS": 5,
    "PASSWORDLESS_RESEND_COOLDOWN_SECONDS": 60,

    # Password reset
    "PASSWORD_RESET_TOKEN_TTL_MINUTES": 60,
    "PASSWORD_RESET_COOLDOWN_SECONDS": 60,

    # Security
    "TOKEN_HMAC_KEY": "",  # Falls back to SECRET_KEY
    "CONSTANT_TIME_BACKEND_RESPONSES": True,
}
```

---

## Testing Examples

```python
import pytest
from apps.authn.services.authentication import AuthenticationService
from apps.authn.services.mfa import MFAService
from apps.authn.exceptions import (
    InvalidCredentialsError,
    MFARequiredError,
    AccountLockedError,
)


@pytest.mark.django_db
def test_password_login(api_client, user_with_password):
    response = api_client.post("/api/auth/login/", {
        "identifier": user_with_password.email,
        "password": "TestPass123!",
    })
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data


@pytest.mark.django_db
def test_mfa_login_flow(api_client, user_with_mfa, rf):
    request = rf.post("/login/", {"identifier": "user@test.com", "password": "Pass123!"})
    from django.contrib.sessions.backends.db import SessionStore
    request.session = SessionStore()

    with pytest.raises(MFARequiredError) as exc_info:
        AuthenticationService.authenticate_with_password(
            request=request,
            identifier=user_with_mfa.email,
            password="Pass123!",
        )

    mfa_token = exc_info.value.mfa_token
    assert mfa_token is not None

    # Complete MFA with TOTP code
    import pyotp
    totp = pyotp.TOTP(user_with_mfa.totp_secret)
    result = AuthenticationService.authenticate_mfa(
        request=request,
        mfa_token=mfa_token,
        code=totp.now(),
    )
    assert result.principal == user_with_mfa


@pytest.mark.django_db
def test_invalid_credentials_locked_out(rf, user_principal):
    from apps.authn.settings import authn_settings
    max_attempts = authn_settings.MAX_FAILED_ATTEMPTS

    request = rf.post("/login/")
    from django.contrib.sessions.backends.db import SessionStore
    request.session = SessionStore()

    for _ in range(max_attempts):
        with pytest.raises(InvalidCredentialsError):
            AuthenticationService.authenticate_with_password(
                request=request,
                identifier=user_principal.email,
                password="wrong",
            )

    # Next attempt should raise AccountLockedError
    with pytest.raises(AccountLockedError):
        AuthenticationService.authenticate_with_password(
            request=request,
            identifier=user_principal.email,
            password="wrong",
        )


@pytest.mark.django_db
def test_mfa_setup_and_activation(user_principal):
    # Initiate
    setup_data = MFAService.setup_totp(user_principal)
    assert "secret" in setup_data
    assert "provisioning_uri" in setup_data

    # Activate with valid code
    import pyotp
    totp = pyotp.TOTP(setup_data["secret"])
    result = MFAService.activate_totp(user_principal, code=totp.now())
    assert len(result["backup_codes"]) == 10
```
