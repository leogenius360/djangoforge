"""Custom querysets for authz models."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.core.models.querysets import SoftDeleteQuerySet


class PermissionQuerySet(SoftDeleteQuerySet):
    """QuerySet for Permission model."""

    def for_content_type(self, content_type):
        """Filter by content type."""
        return self.filter(content_type=content_type)

    def for_action(self, action: str):
        """Filter by action."""
        return self.filter(action=action)


class RoleQuerySet(SoftDeleteQuerySet):
    """QuerySet for Role model."""

    def for_content_type(self, content_type):
        """Filter roles scoped to a content type (or unscoped)."""
        return self.filter(Q(content_type=content_type) | Q(content_type__isnull=True))

    def root_roles(self):
        """Return roles with no parent."""
        return self.filter(parent__isnull=True)

    def system_roles(self):
        """Return system-managed roles."""
        return self.filter(is_system=True)


class RoleAssignmentQuerySet(SoftDeleteQuerySet):
    """QuerySet for RoleAssignment model."""

    def for_principal(self, principal):
        """Filter by principal."""
        return self.filter(principal=principal)

    def for_resource(self, resource):
        """Filter by resource instance (via ContentType + object_id)."""
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(resource)
        return self.filter(content_type=ct, object_id=resource.pk)

    def active(self):
        """Non-deleted and non-expired assignments."""
        now = timezone.now()
        return super().active().filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

    def expired(self):
        """Only expired assignments."""
        now = timezone.now()
        return self.filter(expires_at__lte=now)


class PolicyQuerySet(SoftDeleteQuerySet):
    """QuerySet for Policy model."""

    def enabled(self):
        """Only enabled policies."""
        return self.filter(is_enabled=True)

    def for_resource(self, resource):
        """Policies applicable to a resource instance (type-level or instance-level)."""
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(resource)
        return self.filter(content_type=ct).filter(Q(object_id__isnull=True) | Q(object_id=resource.pk))

    def for_action(self, action: str):
        """Filter by action (or policies with no action filter)."""
        return self.filter(Q(action="") | Q(action=action))

    def by_priority(self):
        """Order by priority ascending (lower value = higher priority)."""
        return self.order_by("priority", "pk")
