# App Architecture

This document describes the modular app architecture for clean separation of concerns.

## App Boundaries & Dependencies

### Core (`apps.core`)
**Purpose**: Foundation layer with shared base models, utilities, and helpers.

**Contains**:
- `BaseModel`, `BaseQuerySet`, `BaseManager` - Foundational model classes
- `security/crypto.py` - Encryption and hashing utilities
- Shared enums and helpers
- Core middleware and monitoring

**Depends on**: Nothing (foundation layer)

---

### Accounts (`apps.accounts`)
**Purpose**: Identity and account lifecycle management.

**Contains**:
- `User` model (AUTH_USER_MODEL) - User identity
- Account lifecycle metadata (lock, suspend, deactivate)
- Profile identifiers (email, phone, external_id)
- `UserProfile` - Personal information
- `AuditLog` - Security audit logging

**Depends on**: `core`

**Note**: For backward compatibility, also re-exports models from `authn` and `sessions`.

---

### Authn (`apps.authn`)
**Purpose**: Authentication flows (proving identity).

**Contains**:
- MFA credentials (`TOTPCredential`, `WebAuthnCredential`, `BackupCode`)
- Password credentials (`PasswordCredential`)
- Verification tokens (`VerificationToken`)
- Login flows and MFA services
- Password policies and challenges

**Depends on**: `core`, `accounts`, `sessions` (service interfaces only)

**Services**:
- `services/mfa.py` - MFA management

---

### Authz (`apps.authz`)
**Purpose**: Authorization (what can they do).

**Contains** (placeholder for future):
- Roles and permissions
- ABAC/RBAC engine
- Policy evaluation
- Org/tenant membership

**Depends on**: `core`, `accounts` (optionally `sessions` if policies require session claims)

---

### Sessions (`apps.sessions`)
**Purpose**: Session platform (multi-principal, risk, device posture, lifecycle).

**Contains**:
- `AuthSession` model - Session state machine
- Session enums (SessionStatus, AuthenticationStatus, etc.)
- Device fingerprinting and trust
- Session risk scoring
- Revocation/logout operations

**Depends on**: `core` (references principals via `settings.AUTH_USER_MODEL`)

**Important**: Sessions should NOT import `authn` or `authz`. It's a platform layer.

**Services**:
- `services/lifecycle.py` - Session creation, revocation, expiry, cleanup
- `services/risk.py` - Risk scoring and anomaly detection
- `services/device.py` - Device identification and trust

---

## Folder Structure

```
apps/
  core/
    models/
      base.py
      mixins.py
      querysets.py
      managers.py
    security/
      crypto.py
      
  accounts/
    models/
      user.py
      profile.py
      audit.py
    services/
    admin/
      
  authn/
    models/
      credentials.py
      challenges.py
    services/
      mfa.py
      login.py (future)
    admin.py
      
  authz/
    models/
      roles.py (future)
      permissions.py (future)
      assignments.py (future)
    services/
      policies.py (future)
    admin.py
      
  sessions/
    models/
      __init__.py
      enums.py
      querysets.py
      managers.py
      session.py
    services/
      lifecycle.py
      risk.py
      device.py
    admin.py
```

## Migration Path

The refactoring maintains backward compatibility:

1. **Existing code continues to work**: All imports from `apps.accounts.models` continue to function through re-exports.

2. **New code should use direct imports**: 
   - Import credentials from `apps.authn.models`
   - Import sessions from `apps.sessions.models`
   - Import services from their respective apps

3. **Gradual migration**: Over time, update imports in existing code to use the new structure.

## Testing

Run tests to ensure functionality is preserved:
```bash
make test
```

## Linting

Ensure code quality:
```bash
make lint
make format
```
