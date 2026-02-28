"""
Permission model.

Defines an action that can be performed on a resource type.  Permissions are
assigned to roles, never directly to principals.
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.authz.enums import PermissionAction
from apps.core.models import SoftDeleteActorModel

from .managers import PermissionManager


class Permission(SoftDeleteActorModel):
    """
    An allowed action on a specific resource type.

    Fields
    ------
    codename
        Unique machine identifier, e.g. ``"accounts.principal.read"``.
    name
        Human-readable label.
    description
        Optional long-form explanation.
    content_type
        The Django ``ContentType`` this permission targets.
    action
        The action category (create / read / update / delete / list / manage).
    metadata
        Arbitrary JSON metadata.
    """

    codename = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text='Unique identifier, e.g. "accounts.principal.read"',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="authz_permissions",
        help_text="Resource type this permission applies to",
    )
    action = models.CharField(
        max_length=20,
        choices=PermissionAction.choices,
        db_index=True,
    )

    metadata = models.JSONField(default=dict, blank=True)

    objects = PermissionManager()

    class Meta:
        db_table = "authz_permissions"
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"
        ordering = ["content_type__app_label", "content_type__model", "action"]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "action"],
                name="authz_perm_unique_ct_action",
            ),
        ]
        indexes = [
            models.Index(
                fields=["content_type", "action"],
                name="authz_perm_ct_action_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.codename

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def build_codename(cls, content_type: ContentType, action: str) -> str:
        """Build the canonical codename from a content type and action."""
        return f"{content_type.app_label}.{content_type.model}.{action}"
