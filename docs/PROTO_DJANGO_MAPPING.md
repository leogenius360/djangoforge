# Protobuf to Django Model Mapping

This document shows the exact mapping between the protobuf schema and Django models.

## User Proto → Django User Model

| Proto Field | Type | Django Field | Type | Notes |
|------------|------|--------------|------|-------|
| `user_id` | string | `id` | UUIDField (inherited) | Auto-generated |
| `tenant_path` | string | ❌ EXCLUDED | - | Not multi-tenant |
| `username` | string | `username` | CharField(64) | Optional, unique |
| `email` | string | `email` | EmailField | Required, unique |
| `email_verified_at` | Timestamp | `email_verified_at` | DateTimeField | NULL = not verified |
| `phone_number` | string | `phone_number` | CharField(17) | E.164 format |
| `phone_verified_at` | Timestamp | `phone_verified_at` | DateTimeField | NULL = not verified |
| `display_name` | string | `display_name` | CharField(100) | Cached from profile |
| `status` | UserStatus | `status` | CharField(30) | Enum: UserStatus |
| `external_id` | string | `external_id` | CharField(255) | Federated identity |
| `external_provider` | string | `external_provider` | CharField(50) | IDP name |
| `last_login_at` | Timestamp | `last_login` | DateTimeField | Django built-in |
| `last_activity_at` | Timestamp | `last_activity_at` | DateTimeField | Custom field |
| `password_changed_at` | Timestamp | `password_changed_at` | DateTimeField | Password tracking |
| `locked_until` | Timestamp | `locked_until` | DateTimeField | Security lock |
| `tags` | repeated string | `tags` | JSONField | Max 50 tags |
| `created_at` | Timestamp | `created_at` | DateTimeField | auto_now_add |
| `updated_at` | Timestamp | `updated_at` | DateTimeField | auto_now |
| `deleted_at` | Timestamp | `deleted_at` | DateTimeField | Soft delete |
| `version` | int64 | `version` | PositiveIntegerField | Optimistic locking |

### Additional Django Fields (Not in Proto)

These fields exist in Django User but not in the proto schema:

| Django Field | Type | Purpose |
|-------------|------|---------|
| `is_staff` | BooleanField (property) | Django admin access |
| `is_active` | BooleanField (property) | Django account active flag |
| `is_superuser` | BooleanField | Django superuser flag |
| `groups` | ManyToManyField | Django permissions |
| `user_permissions` | ManyToManyField | Django permissions |
| `date_joined` | DateTimeField (property) | Django built-in |
| `failed_login_attempts` | PositiveIntegerField | Security tracking |
| `last_login_ip` | GenericIPAddressField | Security tracking |
| `last_login_user_agent` | TextField | Security tracking |

**Note:** Name fields (`given_name`, `family_name`, etc.) are stored in the `UserProfile` model, not the `User` model. MFA-related fields have been moved to separate `TOTPCredential` and `BackupCode` models.
| `passwordless_enabled` | BooleanField | Passwordless auth flag |

---

## UserStatus Proto → Django UserStatus

| Proto Enum | Django Choice | Value |
|-----------|---------------|-------|
| `USER_STATUS_UNSPECIFIED` | ❌ Not used | - |
| `ACTIVE` | `UserStatus.ACTIVE` | "ACTIVE" |
| `INACTIVE` | `UserStatus.INACTIVE` | "INACTIVE" |
| `SUSPENDED` | `UserStatus.SUSPENDED` | "SUSPENDED" |
| `LOCKED` | `UserStatus.LOCKED` | "LOCKED" |
| `DELETED` | `UserStatus.DELETED` | "DELETED" |
| `PENDING_VERIFICATION` | `UserStatus.PENDING_VERIFICATION` | "PENDING_VERIFICATION" |
| `PENDING_APPROVAL` | `UserStatus.PENDING_APPROVAL` | "PENDING_APPROVAL" |
| `EXPIRED` | `UserStatus.EXPIRED` | "EXPIRED" |

---

## UserProfile Proto → Django UserProfile Model

| Proto Field | Type | Django Field | Type | Notes |
|------------|------|--------------|------|-------|
| `profile_id` | string | `id` | UUIDField | Auto-generated |
| `user_id` | string | `user` | OneToOneField(User) | Relationship |
| `tenant_path` | string | ❌ EXCLUDED | - | Not multi-tenant |
| `given_name` | string | `given_name` | CharField(64) | First name |
| `family_name` | string | `family_name` | CharField(64) | Last name |
| `middle_name` | string | `middle_name` | CharField(64) | Middle name |
| `nickname` | string | `nickname` | CharField(64) | Preferred name |
| `picture_url` | string | `picture_url` | URLField | Profile picture |
| `gender` | string | `gender` | CharField(50) | GDPR Article 9 |
| `birth_date` | Timestamp | `birth_date` | DateField | GDPR Article 9 |
| `website_url` | string | `website_url` | URLField | Personal website |
| `bio` | string | `bio` | TextField(1000) | Biography |
| `custom_attributes` | map<string, string> | `custom_attributes` | JSONField | Extensible attrs |
| `created_at` | Timestamp | `created_at` | DateTimeField | auto_now_add |
| `updated_at` | Timestamp | `updated_at` | DateTimeField | auto_now |
| `deleted_at` | Timestamp | `deleted_at` | DateTimeField | Soft delete |
| `version` | int64 | `version` | PositiveIntegerField | Optimistic locking |

---

## Credentials (Extended Beyond Proto)

The proto schema includes basic User authentication, but we've extended it with a comprehensive credential system.

### BaseCredential (Not in Proto - Django Extension)

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUIDField | Primary key |
| `user` | ForeignKey(User) | User relationship |
| `credential_type` | CharField(20) | Type enum |
| `status` | CharField(20) | Status enum |
| `label` | CharField(100) | User-friendly name |
| `last_used_at` | DateTimeField | Usage tracking |
| `expires_at` | DateTimeField | Expiry time |
| `deleted_at` | DateTimeField | Soft delete |
| `version` | PositiveIntegerField | Optimistic lock |
| `created_at` | DateTimeField | Creation time |
| `updated_at` | DateTimeField | Update time |

### PasswordCredential

| Field | Type | Purpose |
|-------|------|---------|
| *Inherits BaseCredential* | - | - |
| `password_hash` | CharField(128) | Hashed password |
| `strength_score` | PositiveSmallIntegerField | Password strength (0-4) |
| `is_compromised` | BooleanField | Breach detection |
| `require_change` | BooleanField | Force password change |

### WebAuthnCredential (FIDO2/Passkey)

| Field | Type | Purpose |
|-------|------|---------|
| *Inherits BaseCredential* | - | - |
| `credential_id` | TextField | Unique credential ID |
| `public_key` | TextField | Public key (base64) |
| `sign_count` | PositiveIntegerField | Replay detection |
| `aaguid` | CharField(36) | Authenticator GUID |
| `transports` | JSONField | Transport methods |
| `backup_eligible` | BooleanField | Can be backed up |
| `backup_state` | BooleanField | Currently backed up |

### TOTPCredential (RFC 6238)

| Field | Type | Purpose |
|-------|------|---------|
| *Inherits BaseCredential* | - | - |
| `secret` | CharField(32) | TOTP secret (base32) |
| `algorithm` | CharField(10) | Hash algorithm |
| `digits` | PositiveSmallIntegerField | OTP length (6/8) |
| `period` | PositiveSmallIntegerField | Time period (30s) |

### BackupCode

| Field | Type | Purpose |
|-------|------|---------|
| *Inherits BaseCredential* | - | - |
| `code_hash` | CharField(128) | Hashed backup code |
| `is_used` | BooleanField | Consumed flag |
| `used_at` | DateTimeField | Usage timestamp |

---

## Data Type Mappings

| Proto Type | Django Type |
|-----------|-------------|
| `string` | CharField / TextField / EmailField / URLField |
| `int64` | PositiveIntegerField / IntegerField |
| `bool` | BooleanField |
| `google.protobuf.Timestamp` | DateTimeField / DateField |
| `repeated string` | JSONField (list) |
| `map<string, string>` | JSONField (dict) |
| `enum` | CharField with TextChoices |

---

## Validation Mappings

| Proto Validation | Django Validation |
|-----------------|-------------------|
| `string.max_len = 512` | `max_length=512` |
| `string.min_len = 3` | `MinLengthValidator(3)` |
| `string.pattern = "^[a-zA-Z0-9_-]+$"` | `RegexValidator(...)` |
| `string.email = true` | `EmailField` |
| `string.uri = true` | `URLField` |
| `int64.gte = 1` | `PositiveIntegerField` |
| `field.required = true` | `blank=False, null=False` |
| `field.required = false` | `blank=True, null=True` |
| `repeated.min_items = 0` | No validation |
| `repeated.max_items = 50` | Application-level validation |
| `enum.defined_only = true` | `choices=...` |

---

## Indexes

All timestamp and status fields are indexed for query performance:

```python
indexes = [
    models.Index(fields=["email"]),
    models.Index(fields=["phone_number"]),
    models.Index(fields=["status"]),
    models.Index(fields=["external_id"]),
    models.Index(fields=["created_at"]),
    models.Index(fields=["deleted_at"]),
    models.Index(fields=["last_activity_at"]),
]
```

---

## Compliance Annotations

All PII and compliance-related comments from proto are preserved in Django docstrings:

```python
# PII: Yes - GDPR Article 4(1) personal identifier.
email = models.EmailField(unique=True, db_index=True)

# COMPLIANCE: GDPR Article 17, SOC 2 CC6.3 (deletion audit trail)
deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

# COMPLIANCE: SOC 2 CC6.1 (data integrity, concurrent modification protection)
version = models.PositiveIntegerField(default=1)
```

---

## Backward Compatibility

To maintain compatibility with existing code:

```python
@property
def is_email_verified(self):
    """Backward compatibility property."""
    return self.email_verified_at is not None

@property
def is_phone_verified(self):
    """Backward compatibility property."""
    return self.phone_verified_at is not None
```

---

## Exclusions

The following proto fields are **intentionally excluded** because this is not a multi-tenant project:

- ❌ `tenant_path` (User)
- ❌ `tenant_path` (UserProfile)

---

## Extensions

The following models are **Django-specific extensions** not present in the proto schema:

- ✅ **BaseCredential** - Flexible credential management
- ✅ **PasswordCredential** - Password authentication
- ✅ **WebAuthnCredential** - FIDO2/Passkey support
- ✅ **TOTPCredential** - TOTP MFA
- ✅ **BackupCode** - Recovery codes
- ✅ **VerificationToken** - Email/phone verification (existing)
- ✅ **AuthSession** - Session tracking (existing)
- ✅ **AuditLog** - Compliance logging (existing)
