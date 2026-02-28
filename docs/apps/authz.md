# `apps/authz` — Authorization

Hybrid RBAC + ABAC authorization system.  Combines hierarchical role-based
access control with attribute-based policies evaluated via a custom DSL
expression engine.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                       apps/authz                            │
│                                                             │
│  models/                                                    │
│    permission.py        Permission                          │
│    role.py              Role (hierarchical)                 │
│    role_permission.py   RolePermission (join table)         │
│    role_assignment.py   RoleAssignment (principal→role→res) │
│    policy.py            Policy (ABAC with DSL condition)    │
│    querysets.py         Per-model querysets                 │
│    managers.py          Per-model managers                  │
│                                                             │
│  services/                                                  │
│    checker.py       AuthorizationChecker  ◄─ primary entry  │
│    role_service.py  RoleService                             │
│    assignment_service.py  AssignmentService                 │
│    policy_service.py  PolicyService                         │
│                                                             │
│  engine/dsl/                                                │
│    lexer.py     Regex tokenizer → Token stream              │
│    parser.py    Recursive-descent parser → AST              │
│    ast_nodes.py Literal, Identifier, GetAttr, BinaryOp ...  │
│    evaluator.py AST evaluator + EvaluationContext           │
│                                                             │
│  api/                                                       │
│    views/ ─► Permissions, Roles, Assignments, Policies, Check│
│    urls.py ─► /api/authz/                                   │
│                                                             │
│  enums.py      PermissionAction, PolicyEffect               │
│  exceptions.py Full exception hierarchy                     │
└────────────────────────────────────────────────────────────┘

Authorization flow in AuthorizationChecker.check():

  1. DENY policies  ──► if any match → DENY immediately
  2. RBAC roles     ──► if role grants action → ALLOW
  3. ALLOW policies ──► if any match → ALLOW
  4. Default        ──► DENY
```

---

## Models

### `Permission`

A single action on a resource type.

**Table:** `authz_permissions`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField(pk)` | |
| `codename` | `CharField(100, unique)` | e.g. `accounts.principal.read` |
| `name` | `CharField(255)` | Human-readable label |
| `description` | `TextField` | |
| `content_type` | `FK → ContentType` | Resource type this applies to |
| `action` | `CharField(20)` | One of `PermissionAction` |
| `metadata` | `JSONField(dict)` | |

**Constraint:** unique on `(content_type, action)`.

**Helper:**
```python
# Build the dotted codename from content_type + action
codename = Permission.build_codename(content_type, action)
# e.g. "accounts.principal.read"
```

---

### `Role`

Hierarchical role with optional resource-type scoping.

**Table:** `authz_roles`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField(pk)` | |
| `codename` | `CharField(100, unique)` | e.g. `project.admin` |
| `name` | `CharField(255)` | |
| `description` | `TextField` | |
| `content_type` | `FK → ContentType(null)` | Scopes which resources this role applies to |
| `parent` | `FK → self(null)` | Parent role for inheritance |
| `is_system` | `BooleanField` | System roles cannot be modified via API |
| `metadata` | `JSONField(dict)` | |

**Hierarchy methods:**
```python
# All ancestors (walk up parent chain, cycle-guarded at depth 20)
ancestors = role.get_ancestors(include_self=False)

# All descendants (BFS down child tree)
descendants = role.get_descendants(include_self=False)

# All permission IDs from this role + all ancestors
perm_ids = role.get_all_permission_ids()  # set of UUIDs
```

**Example hierarchy:**
```
admin_role  (has: manage)
  └── editor_role  (has: update)
        └── viewer_role  (has: read)

admin_role.get_all_permission_ids()  → {manage_id, update_id, read_id}
editor_role.get_all_permission_ids() → {update_id, read_id}
viewer_role.get_all_permission_ids() → {read_id}
```

---

### `RolePermission`

Join table linking roles to permissions.

**Table:** `authz_role_permissions`

| Field | Type |
|---|---|
| `role` | `FK → Role` |
| `permission` | `FK → Permission` |

**Constraint:** unique on `(role, permission)`.

---

### `RoleAssignment`

Assigns a role to a principal on a specific resource instance.

**Table:** `authz_role_assignments`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField(pk)` | |
| `principal` | `FK → Principal` | Who receives the role |
| `role` | `FK → Role` | Which role |
| `content_type` | `FK → ContentType` | Resource type |
| `object_id` | `UUIDField` | Resource instance PK |
| `resource` | `GenericForeignKey` | Shorthand for `content_type + object_id` |
| `granted_by` | `FK → Principal(null)` | Who granted the assignment |
| `granted_at` | `DateTimeField(auto_now_add)` | |
| `expires_at` | `DateTimeField(null)` | Optional TTL |
| `reason` | `CharField(500)` | Why this role was granted |
| `metadata` | `JSONField(dict)` | |

**Constraint:** unique active assignment per `(principal, role, content_type, object_id)` where `deleted_at IS NULL`.

**Property:**
```python
assignment.is_expired  # True when expires_at is in the past
```

---

### `Policy`

ABAC policy with a DSL condition expression.

**Table:** `authz_policies`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField(pk)` | |
| `codename` | `CharField(100, unique)` | |
| `name` | `CharField(255)` | |
| `description` | `TextField` | |
| `effect` | `CharField(10)` | `allow` or `deny` |
| `condition` | `TextField` | DSL expression evaluated at check time |
| `priority` | `IntegerField(default=100)` | Lower value = evaluated first |
| `content_type` | `FK → ContentType` | Resource type scope |
| `object_id` | `UUIDField(null)` | Specific resource instance (optional) |
| `action` | `CharField(20, blank)` | Action filter — empty matches all actions |
| `is_enabled` | `BooleanField` | |
| `is_system` | `BooleanField` | System policies cannot be modified via API |
| `metadata` | `JSONField(dict)` | |

---

## QuerySets

```python
from apps.authz.models import Permission, Role, RoleAssignment, Policy

# Permission
Permission.objects.for_content_type(ct)
Permission.objects.for_action("read")

# Role
Role.objects.for_content_type(ct)
Role.objects.root_roles()    # no parent
Role.objects.system_roles()  # is_system=True

# RoleAssignment
RoleAssignment.objects.for_principal(principal)
RoleAssignment.objects.for_resource(resource)
RoleAssignment.objects.active()        # excludes expired assignments

# Policy
Policy.objects.enabled()
Policy.objects.for_resource(resource)  # matches content_type + optional object_id
Policy.objects.for_action("read")
Policy.objects.by_priority()           # ordered by priority ASC
```

---

## DSL Policy Engine

Policy `condition` fields use a custom expression language evaluated at
authorization-check time.

### Grammar

```
expression  := or_expr
or_expr     := and_expr (("or" | "||") and_expr)*
and_expr    := not_expr (("and" | "&&") not_expr)*
not_expr    := ("not" | "!") not_expr | comparison
comparison  := access (("==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "contains") access)?
access      := primary ("." IDENTIFIER)*
primary     := "true" | "false" | "null" | NUMBER | STRING
             | IDENTIFIER | "(" expression ")" | "[" list_items "]"
```

### Context variables available in conditions

| Variable | Type | Description |
|---|---|---|
| `principal` | `Principal` instance | The entity being checked |
| `resource` | Model instance | The target resource |
| `action` | `str` | The action being performed |
| `environment` | `dict` | Runtime context: `timestamp`, `hour`, `day_of_week`, `is_weekend` |

> **Null propagation:** accessing an attribute on `null` returns `null` instead of raising.

### Condition examples

```python
# Allow only during business hours on weekdays
"environment.hour >= 9 and environment.hour < 17 and not environment.is_weekend"

# Owner-only access
"resource.owner_id == principal.id"

# Restrict to specific actions
"action in [\"read\", \"list\"]"

# Kind-based restriction
"principal.kind == \"user\""

# Combine conditions
"principal.kind == \"user\" and resource.status == \"active\""

# Negate
"not (principal.is_locked or principal.is_suspended)"

# Service accounts only, with scope check
"principal.kind == \"service\" and action == \"read\""
```

### Using the DSL engine directly

```python
from apps.authz.engine.dsl.parser import Parser
from apps.authz.engine.dsl.evaluator import Evaluator, EvaluationContext

# Parse
parser = Parser()
ast = parser.parse("principal.kind == \"user\" and action == \"read\"")

# Build context
context = EvaluationContext(
    principal=principal,
    resource=resource,
    action="read",
    environment={"hour": 14, "is_weekend": False},
)

# Evaluate
evaluator = Evaluator()
result = evaluator.evaluate(ast, context)
# result: bool (or None for null)
```

---

## Services

### `AuthorizationChecker`

```python
from apps.authz.services import AuthorizationChecker

checker = AuthorizationChecker()

# Check (returns decision, never raises)
decision = checker.check(principal, "read", resource)
print(decision.allowed)            # True / False
print(decision.reason)             # "Granted by role: project.viewer"
print(decision.evaluation_time_ms) # 1.23
print(decision.matched_assignments)
print(decision.matched_policies)

# Check with custom environment context
decision = checker.check(
    principal,
    "update",
    resource,
    environment={"hour": 14, "is_weekend": False},
)

# Check or raise PermissionDeniedError on deny
try:
    checker.check_or_raise(principal, "delete", resource)
except PermissionDeniedError as e:
    print(e.reason)  # "No matching permissions or policies"
```

### `RoleService`

```python
from apps.authz.services import RoleService

svc = RoleService()

# Create role
role = svc.create_role(
    codename="project.viewer",
    name="Project Viewer",
    description="Can view project resources",
    content_type=project_ct,  # optional scope
)

# Add permission to role
svc.add_permission(role, read_permission)

# Remove permission
svc.remove_permission(role, read_permission)

# Set parent (validates no cycles)
svc.update_role(role, parent=parent_role)
# Raises RoleHierarchyCycleError if this would create a cycle

# Delete role (soft-delete)
svc.delete_role(role, actor=admin_principal)
```

### `AssignmentService`

```python
from apps.authz.services import AssignmentService
from datetime import timedelta
from django.utils import timezone

svc = AssignmentService()

# Assign a role to a principal on a resource (idempotent — updates expiry if exists)
assignment = svc.assign_role(
    principal=user_principal,
    role=viewer_role,
    resource=project,
    granted_by=admin_principal,
    expires_at=timezone.now() + timedelta(days=30),
    reason="Project onboarding",
)

# Revoke a role assignment
svc.revoke_role(
    principal=user_principal,
    role=viewer_role,
    resource=project,
    actor=admin_principal,
)

# Check if principal has a role on a resource
has_role = svc.has_role(principal, viewer_role, resource)
```

### `PolicyService`

```python
from apps.authz.services import PolicyService
from django.contrib.contenttypes.models import ContentType

svc = PolicyService()

# Validate a condition expression (syntax check only)
svc.validate_condition('principal.kind == "user"')
# Raises DSLSyntaxError if invalid

# Create a policy
policy = svc.create_policy(
    codename="business-hours-only",
    name="Business Hours Access",
    effect="allow",
    condition="environment.hour >= 9 and environment.hour < 17 and not environment.is_weekend",
    content_type=ContentType.objects.get_for_model(Project),
    priority=50,  # evaluated before default policies (higher priority = lower number)
    action="update",
)

# Create a deny policy
deny_policy = svc.create_policy(
    codename="block-deactivated-principals",
    name="Block Deactivated",
    effect="deny",
    condition="principal.is_disabled or principal.is_suspended",
    content_type=project_ct,
    priority=1,  # evaluated first
)

# Enable/disable a policy
svc.enable_policy(policy)
svc.disable_policy(policy)

# Delete a policy
svc.delete_policy(policy, actor=admin)
```

---

## API Endpoints

All endpoints are prefixed with `/api/authz/`.

### Permissions

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/permissions/` | Authenticated | List permissions |
| `POST` | `/permissions/` | Staff | Create permission |
| `GET` | `/permissions/<uuid>/` | Authenticated | Get permission |
| `PATCH` | `/permissions/<uuid>/` | Staff | Update permission |
| `DELETE` | `/permissions/<uuid>/` | Staff | Delete permission |

**Create permission (POST `/api/authz/permissions/`):**
```json
{
  "codename": "projects.project.read",
  "name": "Read Project",
  "description": "View a project and its resources",
  "content_type_id": 42,
  "action": "read"
}
```

### Roles

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/roles/` | Authenticated | List roles |
| `POST` | `/roles/` | Staff | Create role |
| `GET` | `/roles/<uuid>/` | Authenticated | Get role |
| `PATCH` | `/roles/<uuid>/` | Staff | Update role |
| `DELETE` | `/roles/<uuid>/` | Staff | Delete role |
| `GET` | `/roles/<uuid>/permissions/` | Staff | List role permissions |
| `POST` | `/roles/<uuid>/permissions/` | Staff | Add permission to role |

**Create role (POST `/api/authz/roles/`):**
```json
{
  "codename": "project.editor",
  "name": "Project Editor",
  "description": "Can view and edit project resources",
  "parent": "550e8400-e29b-41d4-a716-446655440001"
}
```

### Assignments

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/assignments/` | Authenticated | List assignments |
| `POST` | `/assignments/` | Authenticated | Create assignment |
| `GET` | `/assignments/<uuid>/` | Authenticated | Get assignment |
| `DELETE` | `/assignments/<uuid>/` | Authenticated | Revoke assignment |

**Create assignment (POST `/api/authz/assignments/`):**
```json
{
  "principal": "550e8400-e29b-41d4-a716-446655440000",
  "role": "550e8400-e29b-41d4-a716-446655440001",
  "resource_type": "projects.project",
  "resource_id": "550e8400-e29b-41d4-a716-446655440002",
  "expires_at": "2025-12-31T23:59:59Z",
  "reason": "Quarterly project access"
}
```

### Policies

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/policies/` | Staff | List policies |
| `POST` | `/policies/` | Staff | Create policy |
| `GET` | `/policies/<uuid>/` | Staff | Get policy |
| `PATCH` | `/policies/<uuid>/` | Staff | Update policy |
| `DELETE` | `/policies/<uuid>/` | Staff | Delete policy |

**Create policy (POST `/api/authz/policies/`):**
```json
{
  "codename": "owner-only-delete",
  "name": "Owner-Only Delete",
  "effect": "allow",
  "condition": "resource.owner_id == principal.id",
  "content_type_id": 42,
  "action": "delete",
  "priority": 100,
  "is_enabled": true
}
```

### Authorization Check

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/check/` | Authenticated | Check authorization |

**Check (POST `/api/authz/check/`):**
```json
// Request
{
  "action": "read",
  "resource_type": "projects.project",
  "resource_id": "550e8400-e29b-41d4-a716-446655440000",
  "environment": {}
}

// Response — allowed (200)
{
  "allowed": true,
  "reason": "Granted by role: project.viewer",
  "evaluation_time_ms": 1.23
}

// Response — denied (200 — always 200, caller inspects "allowed")
{
  "allowed": false,
  "reason": "No matching permissions or policies",
  "evaluation_time_ms": 0.87
}
```

---

## Enums

### `PermissionAction`

```python
from apps.authz.enums import PermissionAction

PermissionAction.CREATE   # "create"
PermissionAction.READ     # "read"
PermissionAction.UPDATE   # "update"
PermissionAction.DELETE   # "delete"
PermissionAction.LIST     # "list"
PermissionAction.MANAGE   # "manage"
```

### `PolicyEffect`

```python
from apps.authz.enums import PolicyEffect

PolicyEffect.ALLOW  # "allow"
PolicyEffect.DENY   # "deny"
```

---

## Exception Hierarchy

```
AuthzError
├── PermissionNotFoundError     — permission lookup failed
├── RoleNotFoundError           — role lookup failed
├── RoleHierarchyCycleError     — parent assignment would create a cycle
├── InvalidAssignmentError      — role scope doesn't match resource type
├── PolicyEvaluationError       — policy evaluation failed
├── DSLSyntaxError              — invalid DSL expression syntax
├── DSLEvaluationError          — DSL runtime evaluation error
└── PermissionDeniedError       — authorization check denied
```

```python
from apps.authz.exceptions import (
    PermissionDeniedError,
    RoleHierarchyCycleError,
    DSLSyntaxError,
)

try:
    checker.check_or_raise(principal, "delete", resource)
except PermissionDeniedError as e:
    print(e.reason)  # "Denied by policy: block-weekends"
```

---

## Testing Examples

```python
import pytest
from apps.authz.services import AuthorizationChecker, AssignmentService, RoleService


@pytest.fixture
def setup_rbac(user_principal, admin_principal, project_resource, principal_ct):
    from django.contrib.contenttypes.models import ContentType
    from apps.authz.models import Permission

    project_ct = ContentType.objects.get_for_model(project_resource.__class__)

    role_svc = RoleService()
    assign_svc = AssignmentService()

    # Create permission + role
    read_perm = Permission.objects.create(
        codename="projects.project.read",
        name="Read Project",
        content_type=project_ct,
        action="read",
    )
    viewer_role = role_svc.create_role(
        codename="project.viewer",
        name="Project Viewer",
    )
    role_svc.add_permission(viewer_role, read_perm)

    # Assign role
    assign_svc.assign_role(
        principal=user_principal,
        role=viewer_role,
        resource=project_resource,
        granted_by=admin_principal,
    )
    return viewer_role, read_perm


@pytest.mark.django_db
def test_rbac_allow(user_principal, project_resource, setup_rbac):
    checker = AuthorizationChecker()
    decision = checker.check(user_principal, "read", project_resource)
    assert decision.allowed
    assert "project.viewer" in decision.reason


@pytest.mark.django_db
def test_rbac_deny_without_role(user_principal, project_resource):
    checker = AuthorizationChecker()
    decision = checker.check(user_principal, "delete", project_resource)
    assert not decision.allowed
    assert "No matching" in decision.reason


@pytest.mark.django_db
def test_abac_deny_policy(user_principal, project_resource, admin_principal):
    from django.contrib.contenttypes.models import ContentType
    from apps.authz.services import PolicyService

    policy_svc = PolicyService()
    project_ct = ContentType.objects.get_for_model(project_resource.__class__)

    # Create deny policy for suspended principals
    policy_svc.create_policy(
        codename="deny-suspended",
        name="Deny Suspended Principals",
        effect="deny",
        condition="principal.is_suspended",
        content_type=project_ct,
        priority=1,
    )

    # Suspend the user
    user_principal.suspend(actor=admin_principal, reason="Test")

    checker = AuthorizationChecker()
    decision = checker.check(user_principal, "read", project_resource)
    assert not decision.allowed
    assert "deny-suspended" in decision.reason


@pytest.mark.django_db
def test_dsl_syntax_validation():
    from apps.authz.services import PolicyService
    from apps.authz.exceptions import DSLSyntaxError

    svc = PolicyService()

    # Valid condition
    svc.validate_condition('principal.kind == "user"')  # no exception

    # Invalid condition
    with pytest.raises(DSLSyntaxError):
        svc.validate_condition("principal.kind === user")  # invalid operator


@pytest.mark.django_db
def test_role_hierarchy_cycle_detection(admin_principal):
    from apps.authz.services import RoleService
    from apps.authz.exceptions import RoleHierarchyCycleError

    svc = RoleService()
    parent = svc.create_role(codename="parent-role", name="Parent")
    child = svc.create_role(codename="child-role", name="Child", parent=parent)

    # Try to make parent a child of child (cycle)
    with pytest.raises(RoleHierarchyCycleError):
        svc.update_role(parent, parent=child)
```
