# authz — Authorization

Hybrid RBAC + ABAC authorization system.  Combines hierarchical role-based
access control with attribute-based policies evaluated via a custom DSL
expression engine.

## Architecture

```markdown
Models  →  Services  →  API (DRF)
             ↑
       DSL Engine
  (lexer → parser → evaluator)
```

| Layer | Responsibility |
|-------|---------------|
| **Models** | Permission, Role, RolePermission, RoleAssignment, Policy |
| **Services** | Business logic — role management, assignments, policy CRUD, authorization checks |
| **API** | REST endpoints with serializers delegating writes to services |
| **DSL Engine** | Tokenize, parse, and evaluate policy condition expressions |

All models extend the core base classes (`SoftDeleteActorModel`) and use UUID
primary keys.  Resource scoping is done via Django's `ContentType` framework
and `GenericForeignKey`.

---

## Models

### Permission

Represents a single action that can be performed on a resource type.

| Field | Type | Notes |
|-------|------|-------|
| `codename` | `CharField(100, unique)` | e.g. `accounts.principal.read` |
| `name` | `CharField(255)` | Human-readable label |
| `description` | `TextField(blank)` | |
| `content_type` | `FK → ContentType` | Resource type this permission applies to |
| `action` | `CharField(20)` | One of `PermissionAction` choices |
| `metadata` | `JSONField` | Arbitrary extra data |

**Constraint:** unique on `(content_type, action)`.

Helper: `Permission.build_codename(content_type, action)` produces the
`app_label.model.action` string.

### Role

Hierarchical role with optional resource-type scoping.

| Field | Type | Notes |
|-------|------|-------|
| `codename` | `CharField(100, unique)` | e.g. `project.admin` |
| `name` | `CharField(255)` | |
| `description` | `TextField(blank)` | |
| `content_type` | `FK → ContentType (nullable)` | Limits which resources this role can be assigned to |
| `parent` | `FK → self (nullable)` | Parent role for hierarchy |
| `is_system` | `BooleanField` | System roles cannot be modified via API |
| `metadata` | `JSONField` | |

### RolePermission

Join table linking roles to permissions.

| Field | Type |
|-------|------|
| `role` | `FK → Role` |
| `permission` | `FK → Permission` |

**Constraint:** unique on `(role, permission)`.

### RoleAssignment

Assigns a role to a principal on a specific resource instance.

| Field | Type | Notes |
|-------|------|-------|
| `principal` | `FK → Principal` | Who receives the role |
| `role` | `FK → Role` | Which role |
| `content_type` | `FK → ContentType` | Resource type |
| `object_id` | `UUIDField` | Resource instance PK |
| `resource` | `GenericForeignKey` | |
| `granted_by` | `FK → Principal (nullable)` | Who granted the assignment |
| `granted_at` | `DateTimeField(auto_now_add)` | |
| `expires_at` | `DateTimeField (nullable)` | Optional TTL |
| `reason` | `CharField(500, blank)` | |
| `metadata` | `JSONField` | |

**Constraint:** unique active assignment per `(principal, role, content_type, object_id)` where `deleted_at IS NULL`.

**Property:** `is_expired` — returns `True` when `expires_at` is in the past.

### Policy

ABAC policy with a DSL condition expression.

| Field | Type | Notes |
|-------|------|-------|
| `codename` | `CharField(100, unique)` | |
| `name` | `CharField(255)` | |
| `description` | `TextField(blank)` | |
| `effect` | `CharField(10)` | `allow` or `deny` |
| `condition` | `TextField` | DSL expression |
| `priority` | `IntegerField(default=100)` | Lower value = higher priority |
| `content_type` | `FK → ContentType` | Resource type scope |
| `object_id` | `UUIDField (nullable)` | Specific resource instance (optional) |
| `action` | `CharField(20, blank)` | Action filter — empty matches all actions |
| `is_enabled` | `BooleanField` | |
| `is_system` | `BooleanField` | |
| `metadata` | `JSONField` | |

### Custom QuerySets

| QuerySet | Key Methods |
|----------|------------|
| `PermissionQuerySet` | `for_content_type(ct)`, `for_action(action)` |
| `RoleQuerySet` | `for_content_type(ct)`, `root_roles()`, `system_roles()` |
| `RoleAssignmentQuerySet` | `for_principal(p)`, `for_resource(r)`, `active()` (excludes expired) |
| `PolicyQuerySet` | `enabled()`, `for_resource(r)`, `for_action(a)`, `by_priority()` |

---

## Role Hierarchy

Roles form a tree through the `parent` foreign key.  A child role inherits all
permissions from its ancestors.

```markdown
admin_role  (has: manage)
  └── editor_role  (has: update)
        └── viewer_role  (has: read)
```

In this example `admin_role.get_all_permission_ids()` returns the IDs of
`manage`, `update`, and `read`.

### Methods

| Method | Description |
|--------|------------|
| `get_ancestors(include_self=False)` | Walk up the parent chain (iterative, with cycle guard at depth 20) |
| `get_descendants(include_self=False)` | BFS down the child tree |
| `get_all_permission_ids()` | Permission IDs from this role + all ancestors |

`RoleService` validates that setting a parent would not create a cycle by
checking whether the proposed parent is already a descendant.

---

## DSL Policy Engine

Policy conditions are written in a small expression language evaluated at
authorization-check time.

### Grammar

```markdown
expression  := or_expr
or_expr     := and_expr (("or" | "||") and_expr)*
and_expr    := not_expr (("and" | "&&") not_expr)*
not_expr    := ("not" | "!") not_expr | comparison
comparison  := access (("==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "contains") access)?
access      := primary ("." IDENTIFIER)*
primary     := "true" | "false" | "null" | NUMBER | STRING
             | IDENTIFIER | "(" expression ")" | "[" list_items "]"
```

### Context Variables

| Variable | Type | Description |
|----------|------|------------|
| `principal` | `Principal` instance | The user/service/agent being checked |
| `resource` | Model instance | The target resource |
| `action` | `str` | The action being performed |
| `environment` | `dict` | Dynamic context: `timestamp`, `hour`, `day_of_week`, `is_weekend` |

Attribute access works on both object attributes and dict keys, with null
propagation (accessing an attribute on `null` returns `null` instead of
raising).

### Examples

```python
# Allow only during business hours on weekdays
environment.hour >= 9 and environment.hour < 17 and not environment.is_weekend

# Owner-only access
resource.owner_id == principal.id

# Restrict to specific actions
action in ["read", "list"]

# Combine conditions
principal.kind == "user" and resource.status == "active"

# Negate
not (principal.is_blocked or principal.is_deactivated)
```

### Components

| Component | File | Role |
|-----------|------|------|
| Lexer | `engine/dsl/lexer.py` | Regex-based tokenizer producing `Token` objects |
| Parser | `engine/dsl/parser.py` | Recursive-descent parser producing an AST |
| AST Nodes | `engine/dsl/ast_nodes.py` | `Literal`, `Identifier`, `GetAttr`, `UnaryOp`, `BinaryOp`, `ListLiteral` |
| Evaluator | `engine/dsl/evaluator.py` | Walks the AST against an `EvaluationContext` and returns a value |

---

## Services

### RoleService

```python
from apps.authz.services import RoleService

svc = RoleService()
role = svc.create_role(codename="project.viewer", name="Viewer", ...)
svc.add_permission(role, permission)
svc.update_role(role, parent=parent_role)  # validates no cycles
svc.delete_role(role, actor=principal)
```

### AssignmentService

```python
from apps.authz.services import AssignmentService

svc = AssignmentService()
# Idempotent — updates expiration if assignment already exists
assignment = svc.assign_role(
    principal=user,
    role=role,
    resource=project,
    granted_by=admin,
    expires_at=some_datetime,
    reason="Onboarding",
)
svc.revoke_role(principal=user, role=role, resource=project, actor=admin)
```

### PolicyService

```python
from apps.authz.services import PolicyService

svc = PolicyService()
svc.validate_condition('principal.kind == "user"')  # parse check only
policy = svc.create_policy(
    codename="business-hours",
    name="Business Hours Only",
    effect="allow",
    condition="environment.hour >= 9 and environment.hour < 17",
    content_type=ct,
)
```

### AuthorizationChecker

```python
from apps.authz.services import AuthorizationChecker

checker = AuthorizationChecker()
decision = checker.check(principal, "read", resource)
# decision.allowed -> bool
# decision.reason -> str
# decision.evaluation_time_ms -> float

# Or raise PermissionDeniedError on deny:
checker.check_or_raise(principal, "update", resource)
```

---

## Authorization Flow

The `AuthorizationChecker.check()` method evaluates in this order:

```markdown
1. DENY policies   → if any enabled deny-policy condition matches → DENY
2. RBAC roles       → if any active role assignment grants the action → ALLOW
3. ALLOW policies  → if any enabled allow-policy condition matches → ALLOW
4. Default          → DENY
```

Deny policies are evaluated first so they can override any grants.  RBAC is
checked before ALLOW policies because role assignments are the primary access
mechanism; policies provide supplementary or exceptional access.

---

## API Endpoints

All endpoints are prefixed with `/api/authz/`.

### Permissions

| Method | Path | Description | Access |
|--------|------|------------|--------|
| `GET` | `/permissions/` | List permissions | Authenticated |
| `POST` | `/permissions/` | Create permission | Staff |
| `GET` | `/permissions/<uuid>/` | Get permission | Authenticated |
| `PATCH` | `/permissions/<uuid>/` | Update permission | Staff |
| `DELETE` | `/permissions/<uuid>/` | Delete permission | Staff |

### Roles

| Method | Path | Description | Access |
|--------|------|------------|--------|
| `GET` | `/roles/` | List roles | Authenticated |
| `POST` | `/roles/` | Create role | Staff |
| `GET` | `/roles/<uuid>/` | Get role | Authenticated |
| `PATCH` | `/roles/<uuid>/` | Update role | Staff |
| `DELETE` | `/roles/<uuid>/` | Delete role | Staff |
| `GET` | `/roles/<uuid>/permissions/` | List role permissions | Staff |
| `POST` | `/roles/<uuid>/permissions/` | Add permission to role | Staff |

### Assignments

| Method | Path | Description | Access |
|--------|------|------------|--------|
| `GET` | `/assignments/` | List assignments | Authenticated |
| `POST` | `/assignments/` | Create assignment | Authenticated |
| `GET` | `/assignments/<uuid>/` | Get assignment | Authenticated |
| `DELETE` | `/assignments/<uuid>/` | Revoke assignment | Authenticated |

### Policies

| Method | Path | Description | Access |
|--------|------|------------|--------|
| `GET` | `/policies/` | List policies | Staff |
| `POST` | `/policies/` | Create policy | Staff |
| `GET` | `/policies/<uuid>/` | Get policy | Staff |
| `PATCH` | `/policies/<uuid>/` | Update policy | Staff |
| `DELETE` | `/policies/<uuid>/` | Delete policy | Staff |

### Check

| Method | Path | Description | Access |
|--------|------|------------|--------|
| `POST` | `/check/` | Check authorization | Authenticated |

**Request body:**

```json
{
    "action": "read",
    "resource_type": "accounts.principal",
    "resource_id": "<uuid>",
    "environment": {}
}
```

**Response:**

```json
{
    "allowed": true,
    "reason": "Granted by role: project.viewer",
    "evaluation_time_ms": 1.23
}
```

---

## Enums

### PermissionAction

| Value | Label |
|-------|-------|
| `create` | Create |
| `read` | Read |
| `update` | Update |
| `delete` | Delete |
| `list` | List |
| `manage` | Manage |

### PolicyEffect

| Value | Label |
|-------|-------|
| `allow` | Allow |
| `deny` | Deny |

---

## Exceptions

All exceptions inherit from `AuthzError`.

| Exception | When |
|-----------|------|
| `PermissionNotFoundError` | Permission lookup fails |
| `RoleNotFoundError` | Role lookup fails |
| `RoleHierarchyCycleError` | Setting a parent would create a cycle |
| `InvalidAssignmentError` | Role scope doesn't match resource type |
| `PolicyEvaluationError` | Policy evaluation fails |
| `DSLSyntaxError` | Invalid DSL expression syntax |
| `DSLEvaluationError` | DSL runtime evaluation error |
| `PermissionDeniedError` | Authorization check denied |

---

## Admin

All models are registered in Django admin with search, filtering, and
organized fieldsets.

| Admin Class | Features |
|------------|----------|
| `PermissionAdmin` | Search by codename/name, filter by content_type and action |
| `RoleAdmin` | Search by codename/name, filter by is_system/content_type, inline `RolePermissionInline` |
| `RoleAssignmentAdmin` | Search by principal/role, filter by role and content_type |
| `PolicyAdmin` | Search by codename/name, filter by effect/is_enabled/content_type, ordered by priority |

---

## Testing

```bash
# Run all authz tests
pytest apps/authz/

# Run specific test modules
pytest apps/authz/tests/test_models.py
pytest apps/authz/tests/test_dsl.py
pytest apps/authz/tests/test_services.py
pytest apps/authz/tests/test_api.py
```

### Test Fixtures (`tests/conftest.py`)

| Fixture | Description |
|---------|------------|
| `user_principal` | Regular (non-staff) principal |
| `staff_principal` | Staff/superuser principal |
| `other_principal` | Second regular principal |
| `principal_ct` | ContentType for Principal model |
| `read_perm` | Read permission on Principal |
| `update_perm` | Update permission on Principal |
| `manage_perm` | Manage permission on Principal |
| `viewer_role` | Has read_perm |
| `editor_role` | Child of viewer, has update_perm |
| `admin_role` | Child of editor, has manage_perm |
| `role_service` | `RoleService` instance |
| `assignment_service` | `AssignmentService` instance |
