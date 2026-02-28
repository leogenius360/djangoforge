"""
Role assignment service.

Handles assigning and revoking roles on resource instances.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.authz.exceptions import InvalidAssignmentError
from apps.authz.models import Role, RoleAssignment

if TYPE_CHECKING:
    from datetime import datetime

    from django.db.models import Model

    from apps.accounts.models import Principal

logger = logging.getLogger(__name__)


class AssignmentService:
    """Service for managing role assignments."""

    @transaction.atomic
    def assign_role(
        self,
        *,
        principal: Principal,
        role: Role,
        resource: Model,
        granted_by: Principal | None = None,
        expires_at: datetime | None = None,
        reason: str = "",
    ) -> RoleAssignment:
        """
        Assign a role to a principal on a resource.

        Idempotent — if the assignment already exists the expiration is
        updated and the existing record is returned.

        Raises
        ------
        InvalidAssignmentError
            If the role's ``content_type`` doesn't match the resource type.
        """
        ct = ContentType.objects.get_for_model(resource)

        if role.content_type is not None and role.content_type_id != ct.pk:
            raise InvalidAssignmentError(
                f"Role {role.codename!r} is scoped to "
                f"{role.content_type.app_label}.{role.content_type.model}, "
                f"not {ct.app_label}.{ct.model}"
            )

        existing = (
            RoleAssignment.objects.active()
            .filter(
                principal=principal,
                role=role,
                content_type=ct,
                object_id=resource.pk,
            )
            .first()
        )

        if existing is not None:
            if expires_at != existing.expires_at:
                existing.expires_at = expires_at
                existing.save(update_fields=["expires_at", "updated_at"])
            return existing

        assignment = RoleAssignment.objects.create(
            principal=principal,
            role=role,
            content_type=ct,
            object_id=resource.pk,
            granted_by=granted_by,
            expires_at=expires_at,
            reason=reason,
        )

        logger.info(
            "Assigned role %s to %s on %s:%s",
            role.codename,
            principal.pk,
            ct.model,
            resource.pk,
            extra={"assignment_id": str(assignment.pk)},
        )
        return assignment

    def revoke_role(
        self,
        *,
        principal: Principal,
        role: Role,
        resource: Model,
        actor: Principal | None = None,
    ) -> bool:
        """
        Revoke (soft-delete) a role assignment.

        Returns ``True`` if an assignment was revoked, ``False`` if none existed.
        """
        ct = ContentType.objects.get_for_model(resource)

        assignment = (
            RoleAssignment.objects.active()
            .filter(
                principal=principal,
                role=role,
                content_type=ct,
                object_id=resource.pk,
            )
            .first()
        )

        if assignment is None:
            return False

        assignment.soft_delete(actor=actor)
        logger.info(
            "Revoked role %s from %s on %s:%s",
            role.codename,
            principal.pk,
            ct.model,
            resource.pk,
        )
        return True

    @staticmethod
    def get_assignments_for_principal(
        principal: Principal,
        resource: Model | None = None,
    ):
        """Return active assignments for a principal, optionally scoped to a resource."""
        qs = RoleAssignment.objects.active().for_principal(principal)
        if resource is not None:
            qs = qs.for_resource(resource)
        return qs.select_related("role")

    @staticmethod
    def get_assignments_for_resource(resource: Model):
        """Return all active assignments for a resource."""
        return RoleAssignment.objects.active().for_resource(resource).select_related("principal", "role")
