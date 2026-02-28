"""
Agent account principal subtype for AI/automation agents.

An AgentAccount row links to a canonical Principal row:
- Principal.kind = AGENT
- Sessions reference Principal (not the agent model directly).

Architecture
------------
AgentAccount is a **profile** for agent principals.  All identity,
lifecycle, and expiry fields live on Principal.  AgentAccount stores only
agent-specific configuration (capabilities, scopes, agent_type).

Principal creation is NOT automatic on save.  The API / service layer is
responsible for creating the Principal first and passing it to AgentAccount.
This keeps the model layer free of implicit side effects and makes transactional
boundaries explicit.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import SoftDeleteModel


class AgentAccount(SoftDeleteModel):
    """
    AI / automation agent identity profile.

    Links to ``Principal`` for session ownership and lifecycle management.
    All lifecycle state, expiry, and common identity fields are delegated
    to the linked Principal.

    Fields
    ------
    principal:
        OneToOne link to the AUTH_USER_MODEL (Principal).
    identifier:
        Unique machine-readable identifier for the agent (e.g., "billing-agent-v2").
    agent_type:
        Classification of the agent (e.g., "llm", "workflow", "cron").
    description:
        Free-text description of the agent's purpose and capabilities.
    owner:
        FK to the user Principal who owns/manages this agent.
    allowed_scopes:
        JSON list of OAuth/authorization scopes this agent is allowed.
    capabilities:
        JSON object describing agent capabilities and feature flags.
    metadata:
        Agent-specific JSON metadata (separate from Principal metadata).
    """

    principal = models.OneToOneField(
        "accounts.Principal",
        on_delete=models.PROTECT,
        related_name="agent_account",
        help_text="Canonical principal for session ownership.",
    )

    identifier = models.CharField(
        max_length=150,
        unique=True,
        db_index=True,
        help_text="Unique machine-readable identifier for this agent.",
    )
    agent_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text='Classification of the agent (e.g., "llm", "workflow", "cron").',
    )
    description = models.TextField(blank=True, default="")

    owner = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_agent_accounts",
        limit_choices_to={"kind": "user"},
        help_text="User principal who owns/manages this agent.",
    )

    allowed_scopes = models.JSONField(default=list, blank=True)
    capabilities = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON object describing agent capabilities and feature flags.",
    )

    metadata = models.JSONField(default=dict, blank=True)

    class Meta(SoftDeleteModel.Meta):
        db_table = "agent_accounts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agent_type"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:
        return self.display_name or self.identifier or f"AgentAccount<{self.pk}>"

    def __repr__(self) -> str:
        return f"<AgentAccount(id={self.pk}, identifier={self.identifier!r})>"

    # ------------------------------------------------------------------
    # Delegating properties (identity lives on Principal)
    # ------------------------------------------------------------------

    @property
    def username(self) -> str:
        """Delegate username to Principal."""
        return self.principal.username

    @property
    def display_name(self) -> str:
        """Delegate display name to Principal."""
        return self.principal.display_name

    # ------------------------------------------------------------------
    # Delegating properties (lifecycle lives on Principal)
    # ------------------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """Delegate expiry check to Principal."""
        return self.principal.is_expired

    @property
    def is_locked(self) -> bool:
        """Delegate lock check to Principal."""
        return self.principal.is_locked

    @property
    def is_suspended(self) -> bool:
        """Delegate suspension check to Principal."""
        return self.principal.is_suspended

    @property
    def is_disabled(self) -> bool:
        """Delegate disabled check to Principal."""
        return self.principal.is_disabled

    @property
    def can_authenticate(self) -> bool:
        """
        Agent can authenticate if principal allows it and
        the agent is not soft-deleted.
        """
        if self.is_deleted:
            return False
        return self.principal.can_authenticate

    # ------------------------------------------------------------------
    # Display name sync (explicit, replaces signal-based sync)
    # ------------------------------------------------------------------

    def sync_display_name(self) -> None:
        """
        Explicitly sync display_name to the linked Principal.

        Uses ``identifier`` as the display name.
        """
        self.principal.set_display_name(self.identifier)
