"""
ABAC Policy model.

Policies define attribute-based access rules evaluated via the DSL engine.
They can target a resource type or a specific resource instance.
"""

from __future__ import annotations

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.authz.enums import PolicyEffect
from apps.core.models import SoftDeleteActorModel

from .managers import PolicyManager


class Policy(SoftDeleteActorModel):
    """
    An ABAC policy with a DSL condition expression.

    Fields
    ------
    codename
        Unique machine identifier.
    name
        Human-readable label.
    description
        Optional long-form explanation.
    effect
        ``"allow"`` or ``"deny"``.
    condition
        DSL expression evaluated at authorization time.
    priority
        Lower value = higher priority (evaluated first).
    content_type / object_id / resource
        Targets a resource type, optionally a specific instance.
    action
        If non-empty, the policy only applies to this action.
    is_enabled
        Toggle to disable without deletion.
    is_system
        System policies cannot be modified via the API.
    metadata
        Arbitrary JSON metadata.
    """

    codename = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    effect = models.CharField(
        max_length=10,
        choices=PolicyEffect.choices,
        db_index=True,
    )
    condition = models.TextField(
        help_text='DSL expression, e.g. \'principal.kind == "user" and resource.status == "active"\'',
    )

    priority = models.IntegerField(
        default=100,
        db_index=True,
        help_text="Lower values = higher priority",
    )

    # Resource targeting
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="authz_policies",
        help_text="Resource type this policy applies to",
    )
    object_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Specific resource instance (null = all of type)",
    )
    resource = GenericForeignKey("content_type", "object_id")

    action = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="If set, policy only applies to this action",
    )

    is_enabled = models.BooleanField(default=True, db_index=True)
    is_system = models.BooleanField(default=False)

    metadata = models.JSONField(default=dict, blank=True)

    objects = PolicyManager()

    class Meta:
        db_table = "authz_policies"
        verbose_name = "Policy"
        verbose_name_plural = "Policies"
        ordering = ["priority", "codename"]
        indexes = [
            models.Index(
                fields=["content_type", "object_id"],
                name="authz_policy_ct_oid_idx",
            ),
            models.Index(
                fields=["is_enabled", "priority"],
                name="authz_policy_enabled_prio_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.effect})"
