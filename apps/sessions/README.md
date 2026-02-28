# Sessions App

Enterprise session management for the Django backend.

## Features

- **Custom Session Backend**: Replaces Django's default sessions with AuthSession model
- **Dual Authentication**: Supports both JWT tokens and cookie-based sessions
- **Session Tracking**: Automatic activity tracking and session lifecycle management
- **Multi-device Support**: Track sessions across different devices
- **Security**: Implements session locking, suspension, revocation, and expiry

## Architecture

### Components

1. **AuthSession Model** (`models/session.py`)
   - Enterprise-grade session model with state machine
   - Supports multiple authentication methods
   - Tracks device, location, and activity

2. **Session Backend** (`backends.py`)
   - Custom Django session backend using AuthSession
   - Replaces `django.contrib.sessions.backends.db`

3. **Session Middleware** (`middleware.py`)
   - Tracks session activity automatically
   - Updates last_activity_at on each request
   - Attaches session to request object

4. **Authentication Classes** (`authentication.py`)
   - `CookieJWTAuthentication`: JWT from header or cookie
   - `SessionAuthentication`: Cookie-based session auth
   - `DualAuthentication`: Combined JWT + session auth

5. **Enhanced Auth Backends** (`apps/accounts/backends/`)
   - All authentication backends now create AuthSession on successful login
   - Session ID stored in Django session for cookie-based flows
   - Supports email, username, phone, and passwordless auth

## Configuration

### Settings

```python
# Session backend (optional - can use default Django sessions)
SESSION_ENGINE = 'apps.sessions.backends.DatabaseSessionBackend'

# Middleware (required for activity tracking)
MIDDLEWARE = [
    ...
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.sessions.middleware.SessionTrackingMiddleware',  # Add this
    ...
]

# DRF Authentication (supports both JWT and cookies)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.sessions.authentication.DualAuthentication',  # Primary
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # Fallback
    ),
}
```

## Authentication Flows

### JWT Token Flow

1. User authenticates via login endpoint
2. Backend creates AuthSession
3. JWT token generated (optionally includes session_id)
4. Client sends JWT in Authorization header
5. DualAuthentication validates JWT
6. SessionTrackingMiddleware updates activity

### Cookie Session Flow

1. User authenticates via login endpoint
2. Backend creates AuthSession
3. Session ID stored in Django session cookie
4. Client sends session cookie
5. SessionAuthentication validates session
6. SessionTrackingMiddleware updates activity

### Hybrid Flow

Both flows can work simultaneously:
- JWT for API calls
- Session cookie for web interface
- Same AuthSession tracks both

## Session Management

### Creating Sessions

Sessions are automatically created by authentication backends:

```python
# In authentication backend
session = self._create_session(
    request=request,
    user=user,
    auth_method=AuthenticationMethod.PASSWORD
)
```

### Accessing Sessions

```python
# In views/middleware
session = request.user_session  # Attached by SessionTrackingMiddleware

# Get all active sessions
sessions = AuthSession.objects.filter(
    user=request.user,
    status=SessionStatus.ACTIVE
)
```

### Session Operations

```python
# Lock session
session.lock(duration_minutes=30, reason="Suspicious activity")

# Revoke session
session.revoke(reason="User logged out from another device")

# Extend expiry
session.extend_expiry(duration=timedelta(hours=24))

# Touch activity
session.touch_activity(ip_address="1.2.3.4", path="/api/users/")
```

## Security Features

- **State Machine**: Enforces valid state transitions
- **Automatic Expiry**: Sessions expire based on TTL
- **Lock Support**: Temporary security locks
- **Suspension**: Admin can suspend sessions
- **Activity Tracking**: Monitor session usage
- **Device Fingerprinting**: Detect device changes

## Performance

- **Indexed Queries**: Optimized for common query patterns
- **Lazy Loading**: Session loaded only when needed
- **Batch Operations**: Bulk revoke/cleanup operations
- **Soft Delete**: Terminal sessions can be cleaned up

## Compliance

- ISO 27001 A.9.4: Session management
- SOC 2 CC6.3: Logical and physical access
- NIST 800-63B: Digital authentication
- OWASP: Session management best practices
- PSD2: Strong customer authentication

## Migration from Django Sessions

To migrate from Django's default sessions:

1. Keep `django.contrib.sessions` in INSTALLED_APPS (still needed)
2. Add SessionTrackingMiddleware after AuthenticationMiddleware
3. Update DEFAULT_AUTHENTICATION_CLASSES to use DualAuthentication
4. Authentication backends will create AuthSession automatically
5. Access sessions via `request.user_session`

## Testing

```python
from apps.sessions.models import AuthSession, SessionStatus

# Create test session
session = AuthSession.create_session(
    user=user,
    auth_method=AuthenticationMethod.PASSWORD,
    ip_address="127.0.0.1",
)

# Verify session
assert session.is_valid
assert session.status == SessionStatus.ACTIVE
```
