"""
Role-Permission junction model.

Links permissions to roles.  When checking authorization, all permissions
from a role and its ancestors are considered.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import ActorModel


class RolePermission(ActorModel):
    """
    Associates a permission with a role.

    Fields
    ------
    role
        The role receiving the permission.
    permission
        The permission being granted.
    """

    role = models.ForeignKey(
        "authz.Role",
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    permission = models.ForeignKey(
        "authz.Permission",
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )

    class Meta:
        db_table = "authz_role_permissions"
        verbose_name = "Role Permission"
        verbose_name_plural = "Role Permissions"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"],
                name="authz_role_perm_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role_id} <- {self.permission_id}"
