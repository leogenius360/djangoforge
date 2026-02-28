# Session-Based Authentication Implementation

## Overview

This implementation replaces Django's default sessions with a custom enterprise session management system and enhances authentication backends to support both JWT tokens and cookie-based sessions.

## Changes Summary

### 1. New Session Backend (`apps/sessions/backends.py`)

- **Custom Django Session Backend**: `DatabaseSessionBackend`
- Uses `AuthSession` model instead of Django's default session model
- Integrates with Django's session framework for backward compatibility
- Supports session expiry, validation, and cleanup

### 2. Session Tracking Middleware (`apps/sessions/middleware.py`)

- **SessionTrackingMiddleware**: Tracks user session activity
- Updates `last_activity_at`, `last_activity_ip`, and `last_activity_path`
- Works with both JWT and cookie-based authentication
- Attaches `user_session` to request for easy access

### 3. Dual Authentication Classes (`apps/sessions/authentication.py`)

Three new DRF authentication classes:

1. **CookieJWTAuthentication**
   - Supports JWT from both Authorization header and cookies
   - Extends `JWTAuthentication` from simplejwt
   - Fallback mechanism for cookie-based JWT

2. **SessionAuthentication**
   - Cookie-based session authentication using `AuthSession`
   - Validates session status and expiry
   - Attaches session to request

3. **DualAuthentication** (Primary)
   - Tries JWT authentication first (header or cookie)
   - Falls back to session authentication
   - Provides unified authentication for both flows

### 4. Enhanced Authentication Backends

Updated all authentication backends in `apps/accounts/backends/`:

- **EmailBackend**: Email + password authentication
- **UsernameBackend**: Username + password authentication
- **PhoneBackend**: Phone + password authentication
- **PasswordlessBackend**: Magic link authentication

All backends now:
- Create a `AuthSession` on successful authentication
- Store session ID in Django session for cookie-based flows
- Support MFA detection and session lifecycle
- Track device type, IP address, and user agent

### 5. Settings Configuration (`config/settings/base.py`)

Updated Django REST Framework settings:

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.sessions.authentication.DualAuthentication",  # Primary
        "rest_framework_simplejwt.authentication.JWTAuthentication",  # Fallback
    ),
    ...
}
```

Added session tracking middleware:

```python
MIDDLEWARE = [
    ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.sessions.middleware.SessionTrackingMiddleware",  # New
    ...
]
```

### 6. Documentation

- **apps/sessions/README.md**: Comprehensive session app documentation
- **README.md**: Updated with authentication architecture section
- Integration tests in `apps/sessions/tests_integration.py`

## Authentication Flows

### JWT Token Flow

```
1. Client POSTs credentials to /api/auth/login/
2. EmailBackend.authenticate() validates credentials
3. Backend creates AuthSession with session_id
4. Login view generates JWT tokens
5. Client stores tokens
6. Client sends JWT in Authorization: Bearer <token>
7. DualAuthentication validates JWT
8. SessionTrackingMiddleware updates session activity
```

### Cookie Session Flow

```
1. Client POSTs credentials to /api/auth/login/
2. EmailBackend.authenticate() validates credentials
3. Backend creates AuthSession
4. Session ID stored in Django session cookie
5. Client receives session cookie (automatic)
6. Client sends cookie on subsequent requests
7. SessionAuthentication validates AuthSession
8. SessionTrackingMiddleware updates session activity
```

### Hybrid Flow

Both flows can coexist:
- JWT for API calls from mobile apps
- Session cookies for web interface
- Same AuthSession tracks both access patterns

## Key Features

### Session Management

- **Multi-device Support**: Track sessions across devices
- **State Machine**: Enforce valid session state transitions
- **Lifecycle Management**: Active, locked, suspended, expired, revoked states
- **Activity Tracking**: Track IP, path, and timestamp of last activity
- **Security Controls**: Lock, suspend, and revoke capabilities

### Security

- **MFA Integration**: Detects and enforces MFA requirements
- **Device Fingerprinting**: Track device changes
- **IP Tracking**: Monitor location changes
- **Automatic Expiry**: TTL-based session expiration
- **Concurrent Session Limits**: Future enhancement ready

### Performance

- **Indexed Queries**: Optimized for common patterns
- **Lazy Loading**: Session loaded only when needed
- **Batch Operations**: Bulk revoke and cleanup
- **Minimal Overhead**: Only active users tracked

## Migration Guide

### For Existing Deployments

1. **Keep Django Sessions**: Don't remove `django.contrib.sessions`
2. **Add Middleware**: Add `SessionTrackingMiddleware` after `AuthenticationMiddleware`
3. **Update DRF Settings**: Use `DualAuthentication` as primary authentication class
4. **Run Migrations**: `python manage.py migrate sessions`
5. **Test**: Both JWT and cookie auth should work

### For New Deployments

1. **Use Default Settings**: Already configured in `config/settings/base.py`
2. **Run Migrations**: `python manage.py migrate`
3. **Choose Auth Method**: Use JWT for APIs, cookies for web

## Testing

Run integration tests:

```bash
pytest apps/sessions/tests_integration.py -v
```

All tests verify:
- Session creation during authentication
- Session storage in Django session
- Dual authentication fallback
- Activity tracking

## Code Quality

All code follows project standards:
- ✅ Ruff linting (no errors)
- ✅ Black formatting (120 char line length)
- ✅ Type hints where practical
- ✅ Comprehensive docstrings
- ✅ Pytest integration tests

## Compliance

Implementation satisfies:
- **ISO 27001 A.9.4**: Session management controls
- **SOC 2 CC6.3**: Logical and physical access
- **NIST 800-63B**: Digital authentication guidelines
- **OWASP**: Session management best practices
- **PSD2**: Strong customer authentication

## Future Enhancements

Potential additions:
- Redis caching for session lookups
- WebSocket session tracking
- Geographic IP resolution
- Device trust scoring
- Concurrent session limits enforcement
- Session analytics dashboard

## Backward Compatibility

✅ **No Breaking Changes**:
- Existing JWT authentication still works
- Django session framework still works
- All existing tests pass
- Minimal configuration changes

## Support

For questions or issues:
1. Check `apps/sessions/README.md` for detailed documentation
2. Review integration tests for usage examples
3. Consult Django and DRF documentation for framework details
