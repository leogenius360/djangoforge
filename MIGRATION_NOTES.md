# Migration Notes - Django Apps Restructuring

## What Changed

All Django apps were restructured to follow a consistent enterprise architecture with separated layers for API, models, services, admin, and tests.

## Import Path Changes

If you have code that imports from these apps, update the following paths:

### accounts app
```python
# OLD (no longer works)
from apps.accounts.serializers import UserSerializer
from apps.accounts.views import ProfileView

# NEW (correct)
from apps.accounts.api.serializers import UserSerializer
from apps.accounts.api.views import ProfileView

# Model imports (unchanged)
from apps.accounts.models import UserAccount, Principal
```

### authn app
```python
# OLD
from apps.authn.serializers import LoginSerializer
from apps.authn.views import LoginView

# NEW
from apps.authn.api.serializers import LoginSerializer
from apps.authn.api.views import LoginView

# Model imports (unchanged)
from apps.authn.models import VerificationToken
```

### sessions app
```python
# OLD
from apps.sessions.views import SessionListView
from apps.sessions.serializers import SessionSerializer

# NEW
from apps.sessions.api.views import SessionListView
from apps.sessions.api.serializers import SessionSerializer

# Model imports (unchanged)
from apps.sessions.models import AuthSession
```

### core app
```python
# OLD
from apps.core.views import HealthCheckView

# NEW
from apps.core.api.views import HealthCheckView

# Model imports (unchanged)
from apps.core.models import SoftDeleteModel
```

## URL Pattern Changes

Update your URL includes if you have custom routing:

```python
# OLD
path("auth/", include("apps.authn.urls")),
path("sessions/", include("apps.sessions.urls")),
path("accounts/", include("apps.accounts.urls")),

# NEW
path("auth/", include("apps.authn.api.urls")),
path("sessions/", include("apps.sessions.api.urls")),
path("accounts/", include("apps.accounts.api.urls")),
```

## No Database Changes

✅ No migrations required  
✅ No model changes  
✅ Database schema unchanged  
✅ All data remains intact  

## Testing

All test files moved from `apps/<app>/tests.py` to `apps/<app>/tests/test_<app>.py`

```bash
# Run tests for specific app
pytest apps/accounts/tests/
pytest apps/authn/tests/
pytest apps/sessions/tests/

# Run all tests
pytest apps/
```

## Backward Compatibility

⚠️ **Breaking Changes:**
- API import paths changed (serializers, views)
- URL patterns changed (urls)

✅ **No Breaking Changes:**
- Model imports remain the same
- Database schema unchanged
- Admin still works

## Verification Steps

After pulling these changes:

1. **Check Django configuration:**
   ```bash
   python manage.py check
   ```

2. **Run tests:**
   ```bash
   pytest apps/
   ```

3. **Update your imports** if you see `ModuleNotFoundError`

## Questions?

See `RESTRUCTURING_SUMMARY.md` and `STRUCTURE_DIAGRAM.md` for detailed documentation.
