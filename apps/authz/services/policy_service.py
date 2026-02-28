"""
Policy management service.

Handles policy CRUD and DSL condition validation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from apps.authz.engine.dsl.parser import Parser
from apps.authz.exceptions import DSLSyntaxError
from apps.authz.models import Policy

if TYPE_CHECKING:
    from django.contrib.contenttypes.models import ContentType

    from apps.accounts.models import Principal

logger = logging.getLogger(__name__)


class PolicyService:
    """Service for managing ABAC policies."""

    @transaction.atomic
    def create_policy(
        self,
        *,
        codename: str,
        name: str,
        effect: str,
        condition: str,
        content_type: ContentType,
        description: str = "",
        priority: int = 100,
        object_id=None,
        action: str = "",
        is_enabled: bool = True,
        is_system: bool = False,
    ) -> Policy:
        """Create a new policy after validating its DSL condition."""
        self.validate_condition(condition)

        policy = Policy.objects.create(
            codename=codename,
            name=name,
            description=description,
            effect=effect,
            condition=condition,
            priority=priority,
            content_type=content_type,
            object_id=object_id,
            action=action,
            is_enabled=is_enabled,
            is_system=is_system,
        )
        logger.info(
            "Created policy %s (%s)",
            codename,
            effect,
            extra={"policy_id": str(policy.pk)},
        )
        return policy

    def update_policy(self, policy: Policy, **kwargs) -> Policy:
        """Update a policy.  If *condition* is provided it is re-validated."""
        if policy.is_system:
            raise ValueError("Cannot modify a system policy")

        condition = kwargs.get("condition")
        if condition is not None:
            self.validate_condition(condition)

        for attr, value in kwargs.items():
            setattr(policy, attr, value)

        policy.save()
        logger.info(
            "Updated policy %s",
            policy.codename,
            extra={"policy_id": str(policy.pk)},
        )
        return policy

    def delete_policy(self, policy: Policy, *, actor: Principal | None = None) -> None:
        """Soft-delete a policy."""
        if policy.is_system:
            raise ValueError("Cannot delete a system policy")

        policy.soft_delete(actor=actor)
        logger.info(
            "Deleted policy %s",
            policy.codename,
            extra={"policy_id": str(policy.pk)},
        )

    @staticmethod
    def validate_condition(condition: str) -> bool:
        """
        Parse *condition* to verify it is syntactically valid.

        Returns ``True`` on success, raises :class:`DSLSyntaxError` otherwise.
        """
        try:
            Parser(condition).parse()
        except DSLSyntaxError:
            raise
        except Exception as exc:
            raise DSLSyntaxError(f"Invalid condition: {exc}") from exc
        return True
