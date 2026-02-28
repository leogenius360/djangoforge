"""
Role management service.

Handles role CRUD with hierarchy cycle validation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from apps.authz.exceptions import RoleHierarchyCycleError
from apps.authz.models import Permission, Role, RolePermission

if TYPE_CHECKING:
    from django.contrib.contenttypes.models import ContentType

    from apps.accounts.models import Principal

logger = logging.getLogger(__name__)


class RoleService:
    """Service for managing roles and their permissions."""

    # ------------------------------------------------------------------
    # Role CRUD
    # ------------------------------------------------------------------

    @transaction.atomic
    def create_role(
        self,
        *,
        codename: str,
        name: str,
        description: str = "",
        content_type: ContentType | None = None,
        parent: Role | None = None,
        is_system: bool = False,
    ) -> Role:
        """Create a new role, validating hierarchy constraints."""
        if parent is not None:
            self._validate_no_cycle(parent=parent, child=None)

        role = Role.objects.create(
            codename=codename,
            name=name,
            description=description,
            content_type=content_type,
            parent=parent,
            is_system=is_system,
        )
        logger.info("Created role %s", codename, extra={"role_id": str(role.pk)})
        return role

    def update_role(
        self,
        role: Role,
        *,
        name: str | None = None,
        description: str | None = None,
        parent: Role | None = ...,  # type: ignore[assignment]
    ) -> Role:
        """
        Update a role.

        Pass ``parent=None`` to clear the parent.  Omit ``parent`` (or keep
        the sentinel ``...``) to leave it unchanged.
        """
        if role.is_system:
            raise ValueError("Cannot modify a system role")

        if parent is not ...:
            if parent is not None:
                self._validate_no_cycle(parent=parent, child=role)
            role.parent = parent

        if name is not None:
            role.name = name
        if description is not None:
            role.description = description

        role.save()
        logger.info("Updated role %s", role.codename, extra={"role_id": str(role.pk)})
        return role

    def delete_role(self, role: Role, *, actor: Principal | None = None) -> None:
        """Soft-delete a role."""
        if role.is_system:
            raise ValueError("Cannot delete a system role")

        role.soft_delete(actor=actor)
        logger.info("Deleted role %s", role.codename, extra={"role_id": str(role.pk)})

    # ------------------------------------------------------------------
    # Role-Permission management
    # ------------------------------------------------------------------

    @transaction.atomic
    def add_permission(self, role: Role, permission: Permission) -> RolePermission:
        """Add a permission to a role (idempotent)."""
        rp, created = RolePermission.objects.get_or_create(
            role=role,
            permission=permission,
        )
        if created:
            logger.info(
                "Added permission %s to role %s",
                permission.codename,
                role.codename,
            )
        return rp

    def remove_permission(self, role: Role, permission: Permission) -> None:
        """Remove a permission from a role."""
        deleted, _ = RolePermission.objects.filter(
            role=role,
            permission=permission,
        ).delete()
        if deleted:
            logger.info(
                "Removed permission %s from role %s",
                permission.codename,
                role.codename,
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_no_cycle(*, parent: Role, child: Role | None) -> None:
        """Raise if setting *parent* on *child* would create a cycle."""
        if child is not None and child.pk == parent.pk:
            raise RoleHierarchyCycleError("A role cannot be its own parent")

        if child is not None:
            descendant_ids = {r.pk for r in child.get_descendants()}
            if parent.pk in descendant_ids:
                raise RoleHierarchyCycleError(
                    f"Setting {parent.codename!r} as parent of {child.codename!r} would create a cycle"
                )
