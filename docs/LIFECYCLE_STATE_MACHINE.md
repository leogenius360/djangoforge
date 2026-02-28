# Lifecycle State Machine

This document describes the lifecycle state machine used by models inheriting from `LifecycleMixin`.

## States

### ACTIVE
- **Description**: Default operational state. Entity is fully functional.
- **Required Fields**: None
- **Behavior**: Entity can be accessed and modified normally.

### DISABLED
- **Description**: Administratively disabled. Entity exists but is non-operational.
- **Required Fields**: `disabled_at` must be set
- **Behavior**: Entity is unavailable but can be re-enabled.
- **Use Cases**: Admin actions, policy enforcement, temporary suspension

### LOCKED
- **Description**: Temporarily restricted due to security concerns.
- **Required Fields**: `locked_at` and `locked_until` must both be set
- **Behavior**: 
  - Entity is restricted until `locked_until` timestamp
  - Auto-unlocks when `locked_until` is in the past
  - Typically used for brute-force protection
- **Use Cases**: Failed login attempts, rate limiting, security holds

### SUSPENDED
- **Description**: Policy-based suspension.
- **Required Fields**: `suspended_at` must be set
- **Behavior**: Entity is unavailable pending investigation or remediation.
- **Use Cases**: Terms of service violations, fraud detection, compliance holds

### DELETED
- **Description**: Soft-deleted state. Logically deleted but data retained.
- **Required Fields**: `deleted_at` must be set (if model supports soft delete)
- **Behavior**: Entity is hidden from normal queries but can be restored.
- **Use Cases**: User-initiated deletion, GDPR compliance, audit trail preservation

## State Transition Diagram

```
┌─────────┐
│ ACTIVE  │◄─────────────────────────────┐
└────┬────┘                               │
     │                                    │
     ├──────────┐                         │
     │          │                         │
     ▼          ▼                         │
┌──────────┐ ┌─────────┐                 │
│ DISABLED │ │ LOCKED  │                 │
└────┬─────┘ └────┬────┘                 │
     │            │                       │
     │            ├───────────────────────┤
     │            │                       │
     ▼            ▼                       │
┌────────────┐ ┌──────────┐              │
│ SUSPENDED  │ │ DELETED  │──────────────┘
└────┬───────┘ └──────────┘
     │              ▲
     └──────────────┘
```

## Default Allowed Transitions

| From State | To States |
|------------|-----------|
| ACTIVE | DISABLED, LOCKED, SUSPENDED, DELETED |
| LOCKED | ACTIVE, DISABLED, SUSPENDED, DELETED |
| SUSPENDED | ACTIVE, DISABLED, DELETED |
| DISABLED | ACTIVE, DELETED |
| DELETED | ACTIVE (restoration) |

## Field Requirements by State

| State | disabled_at | locked_at | locked_until | suspended_at | deleted_at |
|-------|-------------|-----------|--------------|--------------|------------|
| ACTIVE | null | null | null | null | null |
| DISABLED | **required** | null | null | null | null |
| LOCKED | null | **required** | **required** | null | null |
| SUSPENDED | null | null | null | **required** | null |
| DELETED | null | null | null | null | **required** |

## Database Constraints

The following database constraints enforce state coherence:

1. **Lock fields consistency**: `locked_at` and `locked_until` must both be null or both be set
2. **Lock duration validity**: `locked_until` must be >= `locked_at`
3. **Disabled state requirement**: `status=DISABLED` requires `disabled_at` to be set
4. **Suspended state requirement**: `status=SUSPENDED` requires `suspended_at` to be set
5. **Locked state requirement**: `status=LOCKED` requires both `locked_at` and `locked_until` to be set

## Convenience Methods

### Transition Methods
- `transition_to(new_status, actor=None, reason="", save=True)` - Generic transition with validation
- `disable(actor=None, reason="Disabled", save=True)` - Shortcut to DISABLED
- `enable(actor=None, reason="Enabled", save=True)` - Shortcut to ACTIVE
- `lock(actor=None, duration=None, reason="Locked", save=True)` - Shortcut to LOCKED
- `unlock(actor=None, reason="Unlocked", save=True)` - Shortcut to ACTIVE (clears lock)
- `suspend(actor=None, reason="Suspended", save=True)` - Shortcut to SUSPENDED
- `unsuspend(actor=None, reason="Unsuspended", save=True)` - Shortcut to ACTIVE (clears suspension)

### Properties
- `is_active` - True if status == ACTIVE
- `is_disabled` - True if status == DISABLED
- `is_suspended` - True if status == SUSPENDED
- `is_locked` - True if locked_until is set and in the future
- `is_expired` - True if expires_at is set and in the past

## Customizing Transitions

Models can override the `ALLOWED_TRANSITIONS` class attribute to customize the state machine:

```python
class CustomModel(EnterpriseModel):
    ALLOWED_TRANSITIONS = {
        CoreStatus.ACTIVE: {CoreStatus.DISABLED, CoreStatus.DELETED},
        CoreStatus.DISABLED: {CoreStatus.ACTIVE},
        CoreStatus.DELETED: set(),  # No transitions from DELETED
    }
```

## Actor Tracking

All transition methods accept an optional `actor` parameter (a `Principal` instance). When provided:
- `disabled_by`, `locked_by`, or `suspended_by` is set to the actor
- The actor is also tracked in audit fields (`updated_by`)

## Validation

### Runtime Validation
The `_validate_lifecycle()` method enforces state coherence before saving:
- Raises `LifecycleStateError` if required fields are missing for the current status
- Runs automatically on every `save()` operation
- Validation occurs BEFORE database constraints to provide friendly error messages

### Transition Validation
The `transition_to()` method validates transitions:
- Raises `LifecycleTransitionError` if the transition is not allowed
- Uses `ALLOWED_TRANSITIONS` (or `DEFAULT_TRANSITIONS` if not customized)

## Examples

### Basic Disable
```python
user.disable(actor=admin_principal, reason="Policy violation")
assert user.status == CoreStatus.DISABLED
assert user.disabled_at is not None
assert user.disabled_by == admin_principal
```

### Temporary Lock
```python
from datetime import timedelta

account.lock(
    actor=system_principal,
    duration=timedelta(hours=1),
    reason="Failed login attempts"
)
assert account.status == CoreStatus.LOCKED
assert account.locked_until > account.locked_at
```

### Restore from Soft Delete
```python
# Soft delete
user.delete()
assert user.deleted_at is not None

# Restore
user.transition_to(CoreStatus.ACTIVE, actor=admin_principal, reason="Restored")
assert user.deleted_at is None
assert user.status == CoreStatus.ACTIVE
```

## Integration with Soft Delete

When a model has both `LifecycleMixin` and `SoftDeleteMixin`:
- `delete()` sets both `deleted_at` and `status=DELETED`
- `hard_delete()` physically removes the row
- Restoration requires calling `transition_to(CoreStatus.ACTIVE)` to clear both fields

## Best Practices

1. **Always provide reasons**: Include meaningful reasons for state changes to aid in auditing
2. **Use convenience methods**: Prefer `disable()`, `lock()`, etc. over direct `transition_to()`
3. **Track actors**: Always pass the `actor` parameter for audit trails
4. **Validate transitions**: Let the state machine enforce valid transitions rather than bypassing with direct field assignment
5. **Use database constraints**: The database-level constraints provide defense in depth against invalid states
