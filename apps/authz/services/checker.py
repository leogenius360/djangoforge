"""
Authorization checker.

Combines RBAC role assignments with ABAC policy evaluation to produce an
authorization decision.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.authz.engine.dsl.evaluator import EvaluationContext, Evaluator
from apps.authz.engine.dsl.parser import Parser
from apps.authz.enums import PolicyEffect
from apps.authz.exceptions import DSLEvaluationError, PermissionDeniedError

if TYPE_CHECKING:
    from django.db.models import Model

    from apps.accounts.models import Principal
    from apps.authz.models import Policy, RoleAssignment

logger = logging.getLogger(__name__)


@dataclass
class AuthzDecision:
    """Result of an authorization check."""

    allowed: bool
    reason: str
    matched_assignments: list[RoleAssignment] = field(default_factory=list)
    matched_policies: list[Policy] = field(default_factory=list)
    evaluation_time_ms: float = 0.0


class AuthorizationChecker:
    """
    Evaluate authorization requests against RBAC roles and ABAC policies.

    Evaluation order
    ----------------
    1. Explicit DENY policies — if any condition matches, deny immediately.
    2. RBAC role assignments — if the principal has a role granting the action
       (including inherited permissions), allow.
    3. ALLOW policies — if any condition matches, allow.
    4. Default: **deny**.
    """

    def check(
        self,
        principal: Principal,
        action: str,
        resource: Model,
        environment: dict[str, Any] | None = None,
    ) -> AuthzDecision:
        """Check if *principal* is authorized to perform *action* on *resource*."""
        start = time.perf_counter()

        from apps.authz.models import Policy, RoleAssignment

        ct = ContentType.objects.get_for_model(resource)
        env = environment if environment is not None else self._default_environment()

        matched_assignments: list[RoleAssignment] = []
        matched_policies: list[Policy] = []

        # 1. DENY policies -------------------------------------------------
        deny_policies = (
            Policy.objects.enabled()
            .filter(effect=PolicyEffect.DENY)
            .for_resource(resource)
            .for_action(action)
            .by_priority()
        )
        for policy in deny_policies:
            if self._evaluate_policy(policy, principal, resource, action, env):
                matched_policies.append(policy)
                return AuthzDecision(
                    allowed=False,
                    reason=f"Denied by policy: {policy.codename}",
                    matched_policies=matched_policies,
                    evaluation_time_ms=self._elapsed_ms(start),
                )

        # 2. RBAC role assignments ------------------------------------------
        assignments = (
            RoleAssignment.objects.active().for_principal(principal).for_resource(resource).select_related("role")
        )

        for assignment in assignments:
            perm_ids = assignment.role.get_all_permission_ids()
            # Check if any of those permissions match the action & content type
            from apps.authz.models import Permission

            has_perm = Permission.objects.filter(
                pk__in=perm_ids,
                content_type=ct,
                action=action,
            ).exists()

            if has_perm:
                matched_assignments.append(assignment)
                return AuthzDecision(
                    allowed=True,
                    reason=f"Granted by role: {assignment.role.codename}",
                    matched_assignments=matched_assignments,
                    evaluation_time_ms=self._elapsed_ms(start),
                )

        # 3. ALLOW policies -------------------------------------------------
        allow_policies = (
            Policy.objects.enabled()
            .filter(effect=PolicyEffect.ALLOW)
            .for_resource(resource)
            .for_action(action)
            .by_priority()
        )
        for policy in allow_policies:
            if self._evaluate_policy(policy, principal, resource, action, env):
                matched_policies.append(policy)
                return AuthzDecision(
                    allowed=True,
                    reason=f"Granted by policy: {policy.codename}",
                    matched_policies=matched_policies,
                    evaluation_time_ms=self._elapsed_ms(start),
                )

        # 4. Default deny ---------------------------------------------------
        return AuthzDecision(
            allowed=False,
            reason="No matching permissions or policies",
            evaluation_time_ms=self._elapsed_ms(start),
        )

    def check_or_raise(
        self,
        principal: Principal,
        action: str,
        resource: Model,
        environment: dict[str, Any] | None = None,
    ) -> AuthzDecision:
        """Like :meth:`check` but raises :class:`PermissionDeniedError` on deny."""
        decision = self.check(principal, action, resource, environment)
        if not decision.allowed:
            raise PermissionDeniedError(decision.reason)
        return decision

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_policy(
        policy: Policy,
        principal: Principal,
        resource: Model,
        action: str,
        environment: dict,
    ) -> bool:
        """Evaluate a single policy condition; return ``True`` if it matches."""
        try:
            ast = Parser(policy.condition).parse()
            ctx = EvaluationContext(
                principal=principal,
                resource=resource,
                action=action,
                environment=environment,
            )
            return bool(Evaluator(ctx).evaluate(ast))
        except DSLEvaluationError as exc:
            logger.warning(
                "Policy %s evaluation failed: %s",
                policy.codename,
                exc,
                extra={"policy_id": str(policy.pk)},
            )
            return False

    @staticmethod
    def _default_environment() -> dict[str, Any]:
        now = timezone.now()
        return {
            "timestamp": now.isoformat(),
            "hour": now.hour,
            "day_of_week": now.weekday(),
            "is_weekend": now.weekday() >= 5,
        }

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return (time.perf_counter() - start) * 1000
