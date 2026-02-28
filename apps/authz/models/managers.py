"""Custom managers for authz models."""

from __future__ import annotations

from apps.core.models.managers import SoftDeleteManager

from .querysets import (
    PermissionQuerySet,
    PolicyQuerySet,
    RoleAssignmentQuerySet,
    RoleQuerySet,
)


class PermissionManager(SoftDeleteManager.from_queryset(PermissionQuerySet)):
    """Manager for Permission model."""


class RoleManager(SoftDeleteManager.from_queryset(RoleQuerySet)):
    """Manager for Role model."""


class RoleAssignmentManager(SoftDeleteManager.from_queryset(RoleAssignmentQuerySet)):
    """Manager for RoleAssignment model."""


class PolicyManager(SoftDeleteManager.from_queryset(PolicyQuerySet)):
    """Manager for Policy model."""
