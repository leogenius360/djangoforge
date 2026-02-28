"""
Role Assignment model.

Assigns a role to a principal on a specific resource instance.
This is the core of resource-scoped RBAC.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteActorModel

from .managers import RoleAssignmentManager


class RoleAssignment(SoftDeleteActorModel):
    """
    Assigns a role to a principal on a specific resource instance.

    Fields
    ------
    principal
        The principal (user / service / agent) receiving the role.
    role
        The role being assigned.
    content_type / object_id / resource
        GenericForeignKey to the resource this assignment applies to.
    granted_by
        The principal who created this assignment.
    granted_at
        When the assignment was created.
    expires_at
        Optional expiration datetime for temporary assignments.
    reason
        Optional reason for the assignment.
    metadata
        Arbitrary JSON metadata.
    """

    principal = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        "authz.Role",
        on_delete=models.CASCADE,
        related_name="assignments",
    )

    # Generic FK to the resource instance
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
    )
    object_id = models.UUIDField(db_index=True)
    resource = GenericForeignKey("content_type", "object_id")

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_role_assignments",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    reason = models.CharField(max_length=500, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    objects = RoleAssignmentManager()

    class Meta:
        db_table = "authz_role_assignments"
        verbose_name = "Role Assignment"
        verbose_name_plural = "Role Assignments"
        ordering = ["-granted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["principal", "role", "content_type", "object_id"],
                condition=models.Q(deleted_at__isnull=True),
                name="authz_assignment_unique_active",
            ),
        ]
        indexes = [
            models.Index(
                fields=["principal", "content_type", "object_id"],
                name="authz_assign_principal_res_idx",
            ),
            models.Index(
                fields=["content_type", "object_id"],
                name="authz_assign_resource_idx",
            ),
            models.Index(
                fields=["expires_at"],
                name="authz_assign_expires_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.principal_id} -> {self.role_id} on {self.content_type_id}:{self.object_id}"

    @property
    def is_expired(self) -> bool:
        """Return ``True`` if the assignment has expired."""
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at
