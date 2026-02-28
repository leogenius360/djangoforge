# authn -- Authentication App

Enterprise-grade authentication subsystem for the BBRI backend. Handles
password login, MFA (TOTP + backup codes), passwordless authentication,
password management, email/phone verification, and account lockout -- all
through a service-first architecture where views are thin HTTP wrappers.

## Architecture

```markdown
                        ┌──────────────┐
                        │  API Views   │  thin HTTP wrappers
                        └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │   Services   │  ALL business logic lives here
                        └──────┬───────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
       ┌──────▼──────┐ ┌──────▼──────┐ ┌───────▼───────┐
       │   Models    │ │  Backends   │ │   External    │
       │ (data+HMAC) │ │ (cred only) │ │  (sessions,   │
       └─────────────┘ └─────────────┘ │   accounts)   │
                                       └───────────────┘

Signals  <──  Services emit lifecycle events  ──>  Signal Handlers (audit)
Exceptions  ──>  DRF Exception Handler  ──>  HTTP responses
```

**Key design principles:**

- **Service-first** -- Views never contain business logic. All
  authentication flows are orchestrated by service classes.
- **HMAC-only token storage** -- Raw tokens and OTP codes are never stored
  in the database. Only HMAC-SHA256 digests are persisted; raw values are
  returned at creation time for immediate delivery.
- **Backends verify credentials only** -- Django auth backends do not
  create sessions. Session creation is handled by `AuthenticationService`.
- **Signal-driven extensibility** -- 18 signals cover the full auth
  lifecycle, wired to handlers in `signal_handlers.py`.

## Directory Layout

```markdown
apps/authn/
├── admin/authn.py Django admin registrations
├── api/
│ ├── serializers/ DRF serializers (auth, mfa, password, verification)
│ ├── urls.py 17 URL patterns (app_name="authn")
│ └── views/ Thin view classes (auth, mfa, password, passwordless, verification)
├── backends/ Django authentication backends
│ ├── base.py BaseAccountsBackend (timing attack prevention, lock checks)
│ ├── email.py EmailBackend (email + password)
│ ├── username.py UsernameBackend (username + password)
│ ├── phone.py PhoneBackend (phone + password, requires verified phone)
│ └── passwordless.py PasswordlessBackend (token-based, delegates to TokenService)
├── exception_handler.py DRF exception handler mapping AuthenticationError -> HTTP
├── exceptions.py Full exception hierarchy with client_message + status_code
├── models/
│ ├── enums.py AuthenticationMethod, CredentialStatus, LoginAttemptResult, etc.
│ ├── credentials.py BaseCredential, PasswordCredential, TOTPCredential, WebAuthnCredential, BackupCode
│ ├── challenges.py VerificationToken (HMAC-based)
│ ├── login_attempts.py LoginAttempt (brute-force tracking)
│ ├── mfa_pending.py MFAPendingAuthentication (DB-backed MFA state)
│ └── password_history.py PasswordHistory (password reuse prevention)
├── services/
│ ├── authentication.py AuthenticationService -- central orchestrator
│ ├── token.py TokenService -- HMAC token create/verify/consume
│ ├── mfa.py MFAService -- TOTP setup/verify, backup codes
│ ├── password.py PasswordService -- change, reset, history, expiry
│ ├── lockout.py LockoutService -- progressive lockout
│ └── verification.py VerificationService -- email/phone verification
├── settings.py AuthnSettings with ~25 configurable options
├── signals.py 18 Django signals
├── signal_handlers.py Handlers + connect_signals()
├── utils/tokens.py HMAC primitives (hmac_hash, hmac_verify, generate_token, generate_otp)
└── tests/ 197 tests across 7 files
```

## API Endpoints

All endpoints are prefixed by the project's API root (e.g. `/api/auth/`).

### Authentication

| Method | Path          | View         | Auth | Description                                       |
| ------ | ------------- | ------------ | ---- | ------------------------------------------------- |
| POST   | `/login/`     | LoginView    | No   | Password login (returns session or MFA challenge) |
| POST   | `/login/mfa/` | MFALoginView | No   | Complete MFA step with TOTP or backup code        |
| POST   | `/logout/`    | LogoutView   | Yes  | End current session (or all sessions)             |

### Password Management

| Method | Path                       | View                     | Auth | Description                                           |
| ------ | -------------------------- | ------------------------ | ---- | ----------------------------------------------------- |
| POST   | `/password/change/`        | PasswordChangeView       | Yes  | Change password (validates current, enforces history) |
| POST   | `/password/reset/`         | PasswordResetRequestView | No   | Request password reset (always returns 200)           |
| POST   | `/password/reset/confirm/` | PasswordResetConfirmView | No   | Confirm reset with token + new password               |

### MFA Management

| Method   | Path                 | View                      | Auth | Description                                                   |
| -------- | -------------------- | ------------------------- | ---- | ------------------------------------------------------------- |
| GET      | `/mfa/status/`       | MFAStatusView             | Yes  | Check MFA status (enabled, backup codes remaining)            |
| GET/POST | `/mfa/setup/`        | MFASetupView              | Yes  | GET: provisioning URI + secret; POST: activate with TOTP code |
| POST     | `/mfa/disable/`      | MFADisableView            | Yes  | Disable MFA (requires password confirmation)                  |
| POST     | `/mfa/backup-codes/` | BackupCodesRegenerateView | Yes  | Regenerate backup codes                                       |

### Passwordless Authentication

| Method | Path                     | View                      | Auth | Description                           |
| ------ | ------------------------ | ------------------------- | ---- | ------------------------------------- |
| POST   | `/passwordless/request/` | PasswordlessRequestView   | No   | Request magic link or OTP             |
| POST   | `/passwordless/verify/`  | PasswordlessVerifyView    | No   | Verify magic link token or OTP        |
| POST   | `/passwordless/totp/`    | PasswordlessTOTPLoginView | No   | Login with email + TOTP code directly |

### Email & Phone Verification

| Method | Path                     | View                         | Auth | Description                      |
| ------ | ------------------------ | ---------------------------- | ---- | -------------------------------- |
| POST   | `/verify/email/request/` | EmailVerificationRequestView | Yes  | Request email verification token |
| POST   | `/verify/email/confirm/` | EmailVerificationConfirmView | No   | Confirm email with token         |
| POST   | `/verify/phone/request/` | PhoneVerificationRequestView | Yes  | Request phone verification OTP   |
| POST   | `/verify/phone/confirm/` | PhoneVerificationConfirmView | No   | Confirm phone with OTP           |

## Services

### AuthenticationService

Central orchestrator for all authentication flows.

```python
from apps.authn.services import AuthenticationService

# Password login (may raise MFARequiredError)
result = AuthenticationService.authenticate_with_password(
    identifier="user@example.com",
    password="...",
    request=request,
)
# result.user, result.session, result.auth_method

# Complete MFA
result = AuthenticationService.complete_mfa_authentication(
    mfa_token="...",
    code="123456",
    request=request,
)

# Passwordless
result = AuthenticationService.request_passwordless_login(
    identifier="user@example.com",
    method="email",
    request=request,
)
result = AuthenticationService.authenticate_passwordless(
    token="...",
    request=request,
)

# Logout
AuthenticationService.logout(user=user, request=request, all_sessions=False)
```

### TokenService

HMAC-based token creation and verification. Raw tokens are never stored.

```python
from apps.authn.services import TokenService

result = TokenService.create_token(
    user=user,
    purpose="email_verify",
    ttl_minutes=30,
    generate_otp_code=True,
    otp_length=6,
)
# result.raw_token  -- deliver this to the user
# result.otp_code   -- deliver this via SMS (if generated)
# result.token_id   -- stored in DB

ok = TokenService.verify_token(user, purpose, raw_token)
ok = TokenService.verify_otp(user, purpose, otp_code)
TokenService.consume_token(user, purpose, raw_token)
```

### PasswordService

Password change, reset, history enforcement, and expiry checking.

```python
from apps.authn.services import PasswordService

PasswordService.change_password(
    user=user,
    current_password="old",
    new_password="new",
    request=request,
)

result = PasswordService.request_password_reset(
    identifier="user@example.com",
    request=request,
)

PasswordService.confirm_password_reset(
    token="...",
    new_password="...",
    request=request,
)

is_expired = PasswordService.check_password_expiry(user)
```

### MFAService

TOTP setup/activation, verification, backup codes.

```python
from apps.authn.services import MFAService

setup = MFAService.setup_totp(user=user)
# setup["provisioning_uri"], setup["secret"]

MFAService.activate_totp(user=user, code="123456")
result = MFAService.verify_mfa(user=user, code="123456")
MFAService.disable_mfa(user=user, password="...", request=request)
codes = MFAService.regenerate_backup_codes(user=user)
status = MFAService.get_status(user=user)
```

### LockoutService

Progressive lockout with doubling duration.

```python
from apps.authn.services import LockoutService

LockoutService.check_lockout(user=user)         # raises AccountLockedError
LockoutService.record_failed_attempt(user, identifier, request)
LockoutService.record_success(user, identifier, request)
```

### VerificationService

Email and phone verification flows.

```python
from apps.authn.services import VerificationService

result = VerificationService.request_email_verification(user=user)
VerificationService.confirm_email_verification(user=user, token="...")

result = VerificationService.request_phone_verification(user=user)
VerificationService.confirm_phone_verification(user=user, otp_code="123456")
```

## Models

### Credential Models

All credential models inherit from `BaseCredential` which provides:
`status`, `label`, `last_used_at`, `expires_at`, and lifecycle methods
(`activate()`, `revoke()`).

| Model                | Table                     | Purpose                          |
| -------------------- | ------------------------- | -------------------------------- |
| `PasswordCredential` | `password_credentials`    | Hashed password + strength score |
| `TOTPCredential`     | `totp_credentials`        | TOTP secret + algorithm config   |
| `WebAuthnCredential` | `webauthn_credentials`    | WebAuthn public key + metadata   |
| `BackupCode`         | `backup_code_credentials` | HMAC-hashed backup codes         |

### Challenge / Token Models

| Model                      | Table                         | Purpose                                               |
| -------------------------- | ----------------------------- | ----------------------------------------------------- |
| `VerificationToken`        | `verification_tokens`         | HMAC-hashed tokens for email/phone/reset/passwordless |
| `MFAPendingAuthentication` | `mfa_pending_authentications` | DB-backed MFA pending state (replaces cache)          |

### Tracking Models

| Model             | Table              | Purpose                                     |
| ----------------- | ------------------ | ------------------------------------------- |
| `LoginAttempt`    | `login_attempts`   | Login attempt recording for lockout + audit |
| `PasswordHistory` | `password_history` | Password reuse prevention                   |

### Enums

| Enum                   | Values                                                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `AuthenticationMethod` | `PASSWORD`, `PASSWORDLESS`, `WEBAUTHN`, `SSO`                                                                        |
| `CredentialStatus`     | `ACTIVE`, `INACTIVE`, `REVOKED`, `EXPIRED`                                                                           |
| `LoginAttemptResult`   | `SUCCESS`, `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `ACCOUNT_DISABLED`, `MFA_REQUIRED`, `MFA_FAILED`, `RATE_LIMITED` |
| `TokenPurpose`         | `EMAIL_VERIFY`, `PHONE_VERIFY`, `PASSWORD_RESET`, `PASSWORDLESS`                                                     |
| `PasswordSetMethod`    | `USER_CHANGE`, `ADMIN_RESET`, `SYSTEM_RESET`, `INITIAL`                                                              |

## Exception Hierarchy

All exceptions inherit from `AuthenticationError` and carry a
`client_message` (safe for end users) and `status_code` (HTTP status).
The `authn_exception_handler` maps these to structured JSON responses.

```markdown
AuthenticationError (401)
├── InvalidCredentialsError (401)       "Invalid credentials."
├── CredentialExpiredError (401)         "Credentials have expired."
├── PasswordReuseError (400)            "Cannot reuse a recent password."
├── PasswordValidationError (400)       "Password does not meet requirements."
├── AccountLockedError (423)            "Account is temporarily locked."
├── AccountDisabledError (403)          "Account has been disabled."
├── MFARequiredError (401)              "Multi-factor authentication required."
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

**Response format:**

```json
{
  "error": "InvalidCredentialsError",
  "detail": "Invalid credentials.",
  "status_code": 401
}
```

## Signals

18 signals cover the full authentication lifecycle. All handlers are
connected in `apps.py` via `connect_signals()` and log to the audit
subsystem (falling back to Python logging if unavailable).

| Signal                         | Providing args                      | Emitted when              |
| ------------------------------ | ----------------------------------- | ------------------------- |
| `login_succeeded`              | user, request, auth_method, session | Successful login          |
| `login_failed`                 | identifier, request, reason, user   | Failed login attempt      |
| `logout_completed`             | user, request, all_sessions         | User logs out             |
| `mfa_challenge_issued`         | user, request                       | MFA challenge sent        |
| `mfa_verified`                 | user, request, method               | MFA successfully verified |
| `mfa_failed`                   | user, request                       | MFA verification failed   |
| `mfa_enabled`                  | user, request                       | MFA activated             |
| `mfa_disabled`                 | user, request                       | MFA disabled              |
| `credential_created`           | user, credential, credential_type   | New credential created    |
| `credential_revoked`           | user, credential, credential_type   | Credential revoked        |
| `password_changed`             | user, request                       | Password changed          |
| `password_reset_requested`     | user, token_id                      | Password reset requested  |
| `account_locked`               | user, locked_until, attempt_count   | Account locked out        |
| `account_unlocked`             | user                                | Account unlocked          |
| `verification_token_created`   | user, purpose, token_id             | Token created             |
| `verification_token_used`      | user, purpose, token_id             | Token consumed            |
| `email_verification_confirmed` | user                                | Email verified            |
| `phone_verification_confirmed` | user                                | Phone verified            |

## Configuration

All settings are namespaced under `AUTHN` in Django settings and accessed
via `apps.authn.settings.authn_settings`:

```python
# config/settings/base.py
AUTHN = {
    # Lockout
    "MAX_FAILED_ATTEMPTS": 5,
    "LOCKOUT_DURATION_MINUTES": 30,
    "PROGRESSIVE_LOCKOUT": True,
    "PROGRESSIVE_LOCKOUT_MAX_MINUTES": 1440,        # 24h cap

    # Password policy
    "PASSWORD_HISTORY_COUNT": 5,
    "PASSWORD_MAX_AGE_DAYS": 90,                     # None to disable

    # MFA
    "MFA_ISSUER_NAME": "BBRI",
    "MFA_BACKUP_CODE_COUNT": 10,
    "TOTP_VALID_WINDOW": 1,

    # MFA pending session
    "MFA_PENDING_TTL_MINUTES": 5,
    "MFA_PENDING_MAX_ATTEMPTS": 5,

    # Verification tokens
    "VERIFICATION_TOKEN_TTL_MINUTES": 30,

    # Passwordless
    "PASSWORDLESS_TOKEN_TTL_MINUTES": 10,
    "PASSWORDLESS_OTP_LENGTH": 6,
    "PASSWORDLESS_OTP_MAX_ATTEMPTS": 5,
    "PASSWORDLESS_RESEND_COOLDOWN_SECONDS": 60,

    # Password reset
    "PASSWORD_RESET_TOKEN_TTL_MINUTES": 60,
    "PASSWORD_RESET_COOLDOWN_SECONDS": 60,

    # Email verification
    "EMAIL_VERIFICATION_TOKEN_TTL_MINUTES": 1440,   # 24h
    "EMAIL_VERIFICATION_COOLDOWN_SECONDS": 60,

    # Phone verification
    "PHONE_VERIFICATION_OTP_TTL_MINUTES": 10,
    "PHONE_VERIFICATION_OTP_LENGTH": 6,
    "PHONE_VERIFICATION_COOLDOWN_SECONDS": 60,
    "PHONE_VERIFICATION_MAX_ATTEMPTS": 5,

    # Security
    "TOKEN_HMAC_KEY": "",                            # falls back to SECRET_KEY
    "CONSTANT_TIME_BACKEND_RESPONSES": True,
}
```

## Security Properties

1. **HMAC-only token storage** -- Raw tokens and OTP codes are never
   persisted. Only HMAC-SHA256 hex digests are stored, compared using
   `hmac.compare_digest()` for constant-time safety.

2. **Timing attack prevention** -- When a user is not found during
   authentication, the password hasher still runs to prevent timing
   side-channels. Controlled by `CONSTANT_TIME_BACKEND_RESPONSES`.

3. **Progressive lockout** -- Failed attempts trigger account lockout.
   When `PROGRESSIVE_LOCKOUT` is enabled, each successive lockout doubles
   in duration (capped at `PROGRESSIVE_LOCKOUT_MAX_MINUTES`).

4. **Password history** -- `PasswordService.change_password()` checks the
   last N passwords (configured by `PASSWORD_HISTORY_COUNT`) and raises
   `PasswordReuseError` if a match is found.

5. **Security stamp invalidation** -- Password and MFA changes call
   `Principal.bump_security_stamp()`, which invalidates all existing
   sessions for the user.

6. **Per-token brute-force protection** -- Each `VerificationToken` and
   `MFAPendingAuthentication` tracks an attempt counter. Exceeding
   `max_attempts` permanently invalidates the token.

7. **Token invalidation on reissue** -- Creating a new token for the same
   user + purpose automatically soft-deletes all prior unused tokens.

8. **No information leakage** -- Password reset and passwordless request
   endpoints always return a success response regardless of whether the
   user exists. Exception `client_message` values are generic and safe.

## Authentication Backends

Backends are configured in `AUTHENTICATION_BACKENDS` in Django settings.
They are responsible _only_ for credential verification -- session
creation is handled by `AuthenticationService`.

| Backend               | Lookup field                  | Notes                                      |
| --------------------- | ----------------------------- | ------------------------------------------ |
| `EmailBackend`        | `email` (case-insensitive)    | Falls back to `username` kwarg             |
| `UsernameBackend`     | `username` (case-insensitive) | Standard username + password               |
| `PhoneBackend`        | `phone_number`                | Requires `phone_verified_at` to be set     |
| `PasswordlessBackend` | token                         | Delegates to `TokenService.verify_token()` |

All backends extend `BaseAccountsBackend` which adds:

- `user_can_authenticate()` -- checks `is_active` and `is_locked`
- `_prevent_timing_attack()` -- runs password hasher even when user not found

## Testing

197 tests across 7 test files, using pytest + pytest-django.

```markdown
tests/
├── conftest.py               Shared fixtures (user, api_client, user_with_mfa, etc.)
├── test_backends.py          33 tests -- all 4 backends + base class
├── test_exception_handler.py 23 tests -- exception-to-HTTP mapping + hierarchy
├── test_models.py            17 tests -- VerificationToken, LoginAttempt, PasswordHistory, MFAPending, credentials
├── test_services.py          28 tests -- TokenService, LockoutService, MFAService, PasswordService, VerificationService
├── test_signals.py           35 tests -- signal emission, handlers, connect_signals, audit fallback
└── test_views.py             61 tests -- all 17 API endpoints via DRF APIClient
```

Run the tests:

```bash
pytest apps/authn/tests/ -v
```

## Dependencies

**Internal apps:**

- `apps.core` -- Base models (`SoftDeleteModel`, `BaseModel`), managers, querysets
- `apps.accounts` -- `UserAccount`, `Principal` (security stamp, lock state)
- `apps.sessions` -- `AuthSession` (session creation/termination)

**Third-party:**

- `djangorestframework` -- API views, serializers, authentication
- `pyotp` -- TOTP generation and verification
- `qrcode` -- QR code generation for MFA setup (optional)
