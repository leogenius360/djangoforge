"""
AuthSession model.

This is the canonical session record for all principal types:
- User (human)
- ServiceAccount (machine)
- APIClient (app)

Token storage
-------------
Raw cookie handles and refresh tokens are not stored here.
They are stored hashed in SessionCredential.

Naming
------
- last_seen_at: last observed activity (preferred over last_activity_at).
"""

from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Principal
from apps.authn.models.enums import AuthenticationStatus, MFAMethod
from apps.core.context import require_actor
from apps.core.models import SoftDeleteModel
from apps.core.models.mixins import BaseActorMixin, LifecycleMixin

from ..enums import SessionChannel
from .managers import AuthSessionManager


class AuthSession(SoftDeleteModel, BaseActorMixin, LifecycleMixin):
    """
    Authentication session for any principal (User, ServiceAccount, APIClient).

    Validity requires:
    - status ACTIVE (from LifecycleMixin)
    - metadata["auth_status"] = AUTHENTICATED (not pending MFA)
    - not expired (absolute or idle TTL)
    - not locked (locked_until in past or null)
    - principal is active and session security stamp matches principal stamp

    Status vs Semantic Timestamps
    -----------------------------
    - status: Lifecycle state (ACTIVE, LOCKED, SUSPENDED, DISABLED, DELETED)
    - revoked_at: When admin force-terminated (status=DISABLED, terminal)
    - logged_out_at: When user voluntarily logged out (status unchanged, non-terminal)

    Note: logout() is non-terminal - it sets logged_out_at but doesn't change status.
    This allows session resumption/remember-me flows where user can re-authenticate.

    Metadata Fields
    ---------------
    Auth metadata stored in metadata JSON field (not DB columns):
    - channel: Session channel (browser/api/service/agent)
    - auth_method: Authentication method (password/webauthn/etc)
    - auth_status: Auth status (authenticated/pending_mfa)
    - mfa_method: MFA method used (totp/webauthn/sms/none)
    - device_type: Device classification (desktop/mobile/tablet)

    Access via properties: session.channel, session.auth_method, etc.
    """

    principal = models.ForeignKey(
        Principal, on_delete=models.CASCADE, related_name="sessions", db_index=True, null=True
    )

    deleted_by = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_%(class)ss",
    )

    # Lifecycle fields (status, disabled_*, locked_*, suspended_*, expires_at) come from LifecycleMixin

    authenticated_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    idle_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Session-specific semantic timestamps (provide context beyond status)
    revoked_at = models.DateTimeField(null=True, blank=True, help_text="When admin force-terminated this session")
    logged_out_at = models.DateTimeField(
        null=True, blank=True, help_text="When user voluntarily logged out (can re-authenticate)"
    )
    user_agent = models.CharField(max_length=500, blank=True, default="")
    ip_first = models.GenericIPAddressField(null=True, blank=True)
    ip_last = models.GenericIPAddressField(null=True, blank=True)

    device_id = models.CharField(max_length=128, blank=True, default="")
    device_fingerprint = models.CharField(max_length=255, blank=True, default="")
    is_trusted_device = models.BooleanField(default=False)

    scopes = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    security_stamp_at_issue = models.BigIntegerField(default=0)

    objects = AuthSessionManager()

    class Meta:
        db_table = "auth_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["principal", "last_seen_at"]),
            models.Index(fields=["device_fingerprint"]),
            models.Index(fields=["deleted_at"]),
        ]
        # Lifecycle constraints are inherited from LifecycleMixin
        constraints = []

    def __str__(self) -> str:
        return f"AuthSession<{self.pk}> principal={self.principal_id}"

    @classmethod
    def get_active_for_principal(cls, principal):
        """Backwards-compatible helper used by session listing views."""
        principal_obj = getattr(principal, "principal", None) or principal
        return cls.objects.for_principal(principal_obj).filter(
            deleted_at__isnull=True,
            disabled_at__isnull=True,
            suspended_at__isnull=True,
        )

    @classmethod
    def create_session(
        cls,
        *,
        principal,
        channel: str | SessionChannel | None = None,
        expires_in: timedelta | None = None,
        auth_method: str = "",
        require_mfa: bool | None = None,
        user_agent: str = "",
        ip_address: str | None = None,
        device_type: str | None = None,
        **kwargs,
    ):
        """Compatibility wrapper around `AuthSession.objects.create_session`.

        Accepts either a `Principal` or a user object with a `.principal` OneToOne.
        Returns the created session instance (raw credentials are intentionally not returned here).
        """
        principal_obj = getattr(principal, "principal", None) or principal
        if principal_obj is None:
            raise ValueError("principal is required")

        if channel is None:
            channel = SessionChannel.API
        elif isinstance(channel, str):
            channel = SessionChannel(channel)

        if expires_in is not None and not isinstance(expires_in, timedelta):
            raise TypeError("expires_in must be a timedelta or None")

        auth_status = kwargs.pop("auth_status", "")
        if not auth_status:
            needs_mfa = bool(require_mfa)
            auth_status = AuthenticationStatus.PENDING_MFA if needs_mfa else AuthenticationStatus.AUTHENTICATED

        metadata = kwargs.pop("metadata", None) or {}
        if device_type is not None:
            metadata.setdefault("device_type", str(device_type))

        session, _cookie_handle_raw, _refresh_token_raw = cls.objects.create_session(
            principal=principal_obj,
            channel=channel,
            auth_method=auth_method,
            auth_status=auth_status,
            mfa_method=MFAMethod.NONE,
            user_agent=user_agent,
            ip_address=ip_address,
            absolute_ttl=expires_in,
            metadata=metadata,
        )
        return session

    @property
    def expired(self) -> bool:
        """Alias for is_expired from LifecycleMixin."""
        return self.is_expired

    @property
    def idle_expired(self) -> bool:
        """Idle expiry check."""
        return bool(self.idle_expires_at and timezone.now() >= self.idle_expires_at)

    @property
    def locked(self) -> bool:
        """Alias for is_locked from LifecycleMixin."""
        return self.is_locked

    # ---------------------------
    # Compatibility properties (older API surface)
    # ---------------------------

    @property
    def ip_address(self) -> str | None:
        """Most recent IP address (prefers ip_last over ip_first)."""
        return self.ip_last or self.ip_first

    # ─────────────────────────────────────────────────────────────────
    # Metadata property accessors
    # Fields migrated to metadata JSON field for flexibility
    # ─────────────────────────────────────────────────────────────────

    @property
    def channel(self) -> str:
        """Session channel (browser/api/service/agent) from metadata."""
        return str((self.metadata or {}).get("channel", "api"))

    @property
    def auth_method(self) -> str:
        """Authentication method used (password/webauthn/etc) from metadata."""
        return str((self.metadata or {}).get("auth_method", ""))

    @property
    def auth_status(self) -> str:
        """Authentication status (authenticated/pending_mfa) from metadata."""
        return str((self.metadata or {}).get("auth_status", ""))

    @property
    def mfa_method(self) -> str:
        """MFA method used (totp/webauthn/sms) from metadata."""
        return str((self.metadata or {}).get("mfa_method", ""))

    @property
    def device_type(self) -> str:
        """Device type (desktop/mobile/tablet) from metadata."""
        return str((self.metadata or {}).get("device_type", ""))

    @property
    def device_name(self) -> str:
        """Device name from metadata."""
        return str((self.metadata or {}).get("device_name", ""))

    @property
    def location_city(self) -> str:
        """Location city from metadata."""
        return str((self.metadata or {}).get("location_city", ""))

    @property
    def location_country(self) -> str:
        """Location country from metadata."""
        return str((self.metadata or {}).get("location_country", ""))

    @property
    def last_activity_at(self):
        """Backwards-compatible alias for last_seen_at."""
        return self.last_seen_at

    def clean(self):
        """Validate model fields before save."""
        super().clean()

        # Ensure metadata is a dict
        if self.metadata is not None and not isinstance(self.metadata, dict):
            from django.core.exceptions import ValidationError

            raise ValidationError({"metadata": "Must be a dictionary"})

    @property
    def is_valid(self) -> bool:
        """In-memory validity check used in business logic."""
        if self.deleted_at:
            return False
        if self.disabled_at or self.suspended_at:
            return False
        # Check auth_status from metadata (if present)
        auth_status = (self.metadata or {}).get("auth_status", "")
        if auth_status and auth_status != AuthenticationStatus.AUTHENTICATED:
            return False
        if self.is_expired or self.idle_expired:
            return False
        if self.is_locked:
            return False
        if not self.principal.can_authenticate:
            return False
        return self.security_stamp_at_issue == self.principal.security_stamp

    def touch(self, *, ip_address: str | None = None) -> None:
        """
        Update last_seen_at (and ip_last if provided).

        Note:
        Extending idle_expires_at is intentionally not automatic here;
        do it in middleware/policy layer to keep behavior explicit.
        """
        now = timezone.now()

        update_kwargs: dict[str, object] = {"last_seen_at": now}
        if ip_address:
            update_kwargs["ip_last"] = ip_address

        # Direct update bypassing save() - this runs on hot path via middleware
        type(self).objects.filter(pk=self.pk).update(**update_kwargs)

        # Keep in-memory instance consistent
        self.last_seen_at = now
        if ip_address:
            self.ip_last = ip_address

    def touch_activity(self, *, ip_address: str | None = None, path: str = "") -> None:
        """Backwards-compatible activity tracking helper."""
        self.touch(ip_address=ip_address)
        if not path:
            return

        metadata = {**(self.metadata or {}), "last_path": path}
        type(self).objects.filter(pk=self.pk).update(metadata=metadata)
        self.metadata = metadata

    def lock(
        self,
        *,
        actor: Principal | None = None,
        duration: timedelta | None = None,
        duration_minutes: int = 30,
        reason: str = "Session locked",
        using: str | None = None,
    ) -> None:
        """Lock this session for a short period (security control)."""
        if duration is None:
            duration = timedelta(minutes=duration_minutes)
        super().lock(actor=actor, duration=duration, reason=reason, using=using)

    def unlock(
        self,
        *,
        actor: Principal | None = None,
        reason: str = "Session unlocked",
        using: str | None = None,
    ) -> None:
        """Unlock this session and return it to ACTIVE state."""
        super().unlock(actor=actor, reason=reason, using=using)

    def revoke(self, reason: str = "Session revoked", *, revoked_by: Principal | None = None) -> None:
        """
        Revoke this session (admin force-termination).
        Sets status=DISABLED and records revoked_at timestamp.
        This is terminal - session cannot be reactivated.
        """
        actor = require_actor(revoked_by)
        self.revoked_at = timezone.now()
        self.disable(actor=actor, reason=reason)

    def logout(self, reason: str = "Logged out") -> None:
        """
        Mark session as logged out (user voluntary logout).
        Records logged_out_at timestamp but does NOT change status.
        Session can later be re-authenticated (e.g., remember me, session resumption).
        """
        self.logged_out_at = timezone.now()
        self.save(update_fields=["logged_out_at", "updated_at"])

    def suspend(
        self,
        *,
        actor: Principal | None = None,
        reason: str = "Session suspended",
        suspended_by: Principal | None = None,
        using: str | None = None,
    ) -> None:
        """
        Suspend this session (admin action).
        Sets suspended_* fields via LifecycleMixin.suspend().
        """
        super().suspend(actor=actor or suspended_by, reason=reason, using=using)

    def unsuspend(
        self,
        *,
        actor: Principal | None = None,
        reason: str = "Session unsuspended",
        using: str | None = None,
    ) -> None:
        """
        Unsuspend this session and return it to ACTIVE state.
        Clears suspension fields via LifecycleMixin.unsuspend().
        """
        super().unsuspend(actor=actor, reason=reason, using=using)

    @classmethod
    def terminate_all_for_principal(
        cls,
        principal: Principal,
        except_session=None,
        reason: str = "All sessions terminated",
        *,
        actor: Principal | None = None,
    ) -> int:
        """
        Bulk revoke all active sessions for a principal.
        Uses bulk update to transition to DISABLED status.
        """
        qs = cls.objects.filter(
            principal=principal,
            disabled_at__isnull=True,
            deleted_at__isnull=True,
        )
        if except_session:
            qs = qs.exclude(pk=except_session.pk)

        resolved_actor = require_actor(actor)
        now = timezone.now()
        return qs.update(
            revoked_at=now,
            disabled_at=now,
            disabled_by=resolved_actor,
            disabled_reason=reason,
        )

    @classmethod
    def cleanup_terminal(cls, older_than_days: int = 30) -> int:
        """
        Soft-delete terminal sessions older than the cutoff.
        Returns number of rows deleted.
        """
        cutoff = timezone.now() - timedelta(days=older_than_days)
        qs = cls.objects.filter(
            updated_at__lt=cutoff,
        ).filter(Q(disabled_at__isnull=False) | Q(deleted_at__isnull=False))
        count = qs.count()
        qs.delete()
        return count
