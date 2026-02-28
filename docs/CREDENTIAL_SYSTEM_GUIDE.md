# Credential System Usage Guide

## Overview

The new credential system supports multiple authentication methods per user, allowing flexible and secure authentication options.

## Usage Examples

### 1. Password Credentials

```python
from apps.accounts.models import User, PasswordCredential, CredentialStatus

# Create a user
user = User.objects.create_user(email="user@example.com")

# Create password credential
password_cred = PasswordCredential.objects.create(
    user=user,
    label="Primary Password",
    status=CredentialStatus.ACTIVE
)
password_cred.set_password("SecurePassword123!")

# Verify password
if password_cred.check_password("SecurePassword123!"):
    password_cred.mark_used()
    print("Password correct!")
```

### 2. WebAuthn/Passkey Credentials

```python
from apps.accounts.models import WebAuthnCredential

# Register a new passkey
passkey = WebAuthnCredential.objects.create(
    user=user,
    label="iPhone 15 Pro",
    credential_id="base64_encoded_id",
    public_key="base64_encoded_public_key",
    aaguid="authenticator_guid",
    transports=["internal"],
    backup_eligible=True,
    backup_state=True,
    status=CredentialStatus.ACTIVE
)

# During authentication
passkey.increment_sign_count()
```

### 3. TOTP Credentials

```python
from apps.accounts.models import TOTPCredential
import pyotp

# Create TOTP credential
totp_cred = TOTPCredential.objects.create(
    user=user,
    label="Google Authenticator",
    secret=pyotp.random_base32(),
    algorithm="SHA1",
    digits=6,
    period=30,
    status=CredentialStatus.ACTIVE
)

# Generate QR code URI for user
totp = pyotp.TOTP(totp_cred.secret)
provisioning_uri = totp.provisioning_uri(
    name=user.email,
    issuer_name="Your App"
)

# Verify TOTP token
if totp.verify("123456", valid_window=1):
    totp_cred.mark_used()
```

### 4. Backup Codes

```python
from apps.accounts.models import BackupCode
from django.contrib.auth.hashers import make_password
import secrets

# Generate backup codes
def generate_backup_codes(user, count=10):
    codes = []
    for _ in range(count):
        raw_code = secrets.token_hex(4).upper()
        BackupCode.objects.create(
            user=user,
            code_hash=make_password(raw_code),
            status=CredentialStatus.ACTIVE
        )
        codes.append(raw_code)
    return codes

# Verify and consume backup code
backup_code = BackupCode.objects.filter(
    user=user,
    is_used=False,
    status=CredentialStatus.ACTIVE
).first()

if backup_code and backup_code.verify_and_consume("ABCD1234"):
    print("Backup code verified and consumed")
```

## Multi-Factor Authentication Flow

### Setup MFA with TOTP

```python
def setup_mfa(user):
    # Generate TOTP credential
    totp_cred = TOTPCredential.objects.create(
        user=user,
        label="MFA App",
        secret=pyotp.random_base32(),
        status=CredentialStatus.ACTIVE
    )
    
    # Generate backup codes
    backup_codes = []
    for _ in range(10):
        raw_code = secrets.token_hex(4).upper()
        BackupCode.objects.create(
            user=user,
            code_hash=make_password(raw_code),
            status=CredentialStatus.ACTIVE
        )
        backup_codes.append(raw_code)
    
    # Enable MFA on user
    user.mfa_enabled = True
    user.save()
    
    return {
        "totp_uri": pyotp.TOTP(totp_cred.secret).provisioning_uri(
            name=user.email,
            issuer_name="Your App"
        ),
        "backup_codes": backup_codes
    }
```

### Verify MFA During Login

```python
def verify_mfa(user, token):
    # Try TOTP first
    totp_creds = TOTPCredential.objects.filter(
        user=user,
        status=CredentialStatus.ACTIVE,
        deleted_at__isnull=True
    )
    
    for totp_cred in totp_creds:
        totp = pyotp.TOTP(totp_cred.secret)
        if totp.verify(token, valid_window=1):
            totp_cred.mark_used()
            return True
    
    # Try backup code
    backup_codes = BackupCode.objects.filter(
        user=user,
        is_used=False,
        status=CredentialStatus.ACTIVE,
        deleted_at__isnull=True
    )
    
    for backup_code in backup_codes:
        if backup_code.verify_and_consume(token):
            return True
    
    return False
```

## Query Examples

### Get All Active Credentials for a User

```python
from apps.accounts.models import BaseCredential

active_credentials = BaseCredential.objects.filter(
    user=user,
    status=CredentialStatus.ACTIVE,
    deleted_at__isnull=True
)

for cred in active_credentials:
    print(f"{cred.credential_type}: {cred.label}")
```

### Get Specific Credential Types

```python
from apps.accounts.models import CredentialType

# Get all passkeys
passkeys = WebAuthnCredential.objects.filter(
    user=user,
    status=CredentialStatus.ACTIVE,
    deleted_at__isnull=True
)

# Get password credentials
passwords = PasswordCredential.objects.filter(
    user=user,
    status=CredentialStatus.ACTIVE,
    deleted_at__isnull=True
)
```

### Revoke All Credentials for a User

```python
def revoke_all_credentials(user):
    credentials = BaseCredential.objects.filter(
        user=user,
        deleted_at__isnull=True
    )
    
    for cred in credentials:
        cred.revoke()
```

## User Profile Management

### Create/Update Profile

```python
from apps.accounts.models import UserProfile

# Create profile
profile = UserProfile.objects.create(
    user=user,
    given_name="John",
    family_name="Doe",
    nickname="Johnny",
    gender="Male",
    birth_date="1990-01-15",
    bio="Software developer",
    website_url="https://johndoe.com",
    custom_attributes={
        "department": "Engineering",
        "employee_id": "EMP001"
    }
)

# Access profile
print(profile.full_name)  # "John Doe"
print(profile.display_name)  # "Johnny" (nickname takes precedence)

# User display_name is auto-synced
print(user.display_name)  # "Johnny"
```

## User Status Management

### Status Transitions

```python
from apps.accounts.models import UserStatus

# Activate user after verification
user.status = UserStatus.ACTIVE
user.email_verified_at = timezone.now()
user.save()

# Suspend user (admin action)
user.status = UserStatus.SUSPENDED
user.save()

# Lock user (security event)
user.lock_account(duration_minutes=30)
# status is automatically set to LOCKED

# Unlock user
user.unlock_account()
# status is restored to ACTIVE if it was LOCKED

# Soft delete user (GDPR)
user.soft_delete()
# status is set to DELETED, deleted_at is set

# Restore deleted user
user.restore()
# status is set to INACTIVE, deleted_at is cleared
```

## Optimistic Locking

### Prevent Concurrent Updates

```python
from django.db import transaction

@transaction.atomic
def update_user_safely(user_id, new_data):
    user = User.objects.select_for_update().get(id=user_id)
    expected_version = user.version
    
    # Update user
    user.email = new_data["email"]
    user.save()
    
    # Version is automatically incremented
    user.refresh_from_db()
    assert user.version == expected_version + 1
```

## Soft Delete Queries

### Exclude Deleted Records

```python
# Default manager excludes deleted users
active_users = User.objects.all()  # deleted_at IS NULL

# Include deleted users
all_users = User.objects.all_with_deleted()

# Only deleted users
deleted_users = User.objects.deleted_only()
```

## Activity Tracking

### Update Last Activity

```python
# Middleware example
class ActivityTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated:
            request.user.update_activity()
        
        response = self.get_response(request)
        return response
```

## Best Practices

1. **Always use credentials for authentication** - Don't directly check `User.password`
2. **Mark credentials as used** - Call `mark_used()` after successful authentication
3. **Check credential status** - Only use `ACTIVE` credentials
4. **Soft delete instead of hard delete** - Use `soft_delete()` for GDPR compliance
5. **Use optimistic locking** - Check `version` field for concurrent updates
6. **Track activity** - Update `last_activity_at` during user sessions
7. **Label credentials** - Provide user-friendly labels for easier management
8. **Set expiry for temporary credentials** - Use `expires_at` for OTP tokens
9. **Use transactions** - Wrap credential operations in database transactions
10. **Index performance** - All timestamp and status fields are indexed

## Migration from Old System

### Convert Existing Passwords to Credentials

```python
from apps.accounts.models import User, PasswordCredential

# For existing users, create password credential
for user in User.objects.all():
    if user.password:  # User has a password hash
        PasswordCredential.objects.create(
            user=user,
            password_hash=user.password,  # Copy existing hash
            label="Primary Password",
            status=CredentialStatus.ACTIVE
        )
```

### Convert MFA Settings

```python
# For users with MFA enabled
for user in User.objects.filter(mfa_enabled=True):
    if user.mfa_secret:
        TOTPCredential.objects.create(
            user=user,
            secret=user.mfa_secret,
            label="MFA App",
            algorithm="SHA1",
            digits=6,
            period=30,
            status=CredentialStatus.ACTIVE
        )
```
