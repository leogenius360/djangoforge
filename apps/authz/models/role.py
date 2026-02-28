"""
Role model with hierarchy support.

Roles form a tree through ``parent`` self-referential FK.  A child role
inherits all permissions from its ancestors.
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.authz.constants import MAX_ROLE_HIERARCHY_DEPTH
from apps.core.models import SoftDeleteActorModel

from .managers import RoleManager


class Role(SoftDeleteActorModel):
    """
    A named collection of permissions with optional hierarchy.

    Fields
    ------
    codename
        Unique machine identifier, e.g. ``"project.admin"``.
    name
        Human-readable display name.
    description
        Optional long-form explanation.
    content_type
        If set, this role can only be assigned to resources of this type.
    parent
        Parent role for hierarchy — child inherits parent's permissions.
    is_system
        System roles cannot be modified or deleted via the API.
    metadata
        Arbitrary JSON metadata.
    """

    codename = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="authz_roles",
        help_text="Resource type this role is scoped to (optional)",
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text="Parent role for permission inheritance",
    )

    is_system = models.BooleanField(default=False)

    metadata = models.JSONField(default=dict, blank=True)

    objects = RoleManager()

    class Meta:
        db_table = "authz_roles"
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        ordering = ["codename"]
        indexes = [
            models.Index(fields=["content_type"], name="authz_role_ct_idx"),
            models.Index(fields=["parent"], name="authz_role_parent_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    # ------------------------------------------------------------------
    # Hierarchy helpers
    # ------------------------------------------------------------------

    def get_ancestors(self, *, include_self: bool = False) -> list[Role]:
        """
        Return ancestor roles (parent, grandparent, …) via iterative traversal.

        Includes a visited-set guard to break on unexpected cycles.
        """
        ancestors: list[Role] = []
        if include_self:
            ancestors.append(self)

        visited: set = {self.pk}
        current = self.parent
        depth = 0

        while current is not None and depth < MAX_ROLE_HIERARCHY_DEPTH:
            if current.pk in visited:
                break
            visited.add(current.pk)
            ancestors.append(current)
            current = current.parent
            depth += 1

        return ancestors

    def get_descendants(self, *, include_self: bool = False) -> list[Role]:
        """Return descendant roles (children, grandchildren, …) via BFS."""
        descendants: list[Role] = []
        if include_self:
            descendants.append(self)

        visited: set = {self.pk}
        queue = list(self.children.all())

        while queue:
            role = queue.pop(0)
            if role.pk in visited:
                continue
            visited.add(role.pk)
            descendants.append(role)
            queue.extend(role.children.all())

        return descendants

    def get_all_permission_ids(self) -> set:
        """Return permission IDs from this role and all ancestors."""
        from apps.authz.models import RolePermission

        role_ids = [r.pk for r in self.get_ancestors(include_self=True)]
        return set(RolePermission.objects.filter(role_id__in=role_ids).values_list("permission_id", flat=True))
