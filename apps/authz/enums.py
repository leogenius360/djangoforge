"""Authorization-specific enumerations."""

from __future__ import annotations

from django.db.models import TextChoices


class PermissionAction(TextChoices):
    """Standard permission actions for resource-based authorization."""

    CREATE = "create", "Create"
    READ = "read", "Read"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    LIST = "list", "List"
    MANAGE = "manage", "Manage"


class PolicyEffect(TextChoices):
    """ABAC policy effect — allow or deny access."""

    ALLOW = "allow", "Allow"
    DENY = "deny", "Deny"
