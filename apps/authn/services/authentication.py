"""
Authentication service -- central orchestrator for all auth flows.

Coordinates password login, MFA challenge/completion, passwordless login,
and logout.  Delegates to ``LockoutService``, ``MFAService``, ``TokenService``,
and the sessions app.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.auth import authenticate as django_authenticate

from apps.authn.audit import authn_audit
from apps.authn.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    InvalidCredentialsError,
    MFAPendingExpiredError,
    MFARequiredError,
    MFAVerificationFailedError,
)
from apps.authn.models import (
    AuthenticationMethod,
    AuthenticationStatus,
    LoginAttemptResult,
    MFAMethod,
    MFAPendingAuthentication,
    TokenPurpose,
)
from apps.authn.settings import authn_settings
from apps.authn.utils.tokens import generate_token, hmac_hash

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticationResult:
    """Result of a successful authentication."""

    principal: object
    session: object
    auth_method: str
    mfa_method: str = MFAMethod.NONE
    is_new_session: bool = True
    extra: dict = field(default_factory=dict)
    # JWT credentials issued at login; empty string when not applicable.
    access_token: str = ""
    refresh_token: str = ""
    expires_in: int = 0


class AuthenticationService:
    """Central orchestrator for authentication flows.

    Responsibilities:
    - Password-based login with lockout enforcement
    - MFA challenge issuance and completion
    - Passwordless (magic link / OTP) login
    - Session creation via sessions app
    - Logout (single session and all sessions)
    """

    # ── Password login ───────────────────────────────────────────────

    @staticmethod
    def authenticate_with_password(
        *,
        request: HttpRequest,
        identifier: str,
        password: str,
    ) -> AuthenticationResult:
        """Authenticate with identifier (email/username) and password.

        Flow:
        1. Resolve principal via Django's ``authenticate()``.
        2. Check lockout status.
        3. Verify credentials.
        4. If MFA enabled, create MFA pending and raise ``MFARequiredError``.
        5. Otherwise, create session and return result.

        Raises:
            AccountLockedError: Account is locked.
            AccountDisabledError: Account is disabled/inactive.
            InvalidCredentialsError: Bad credentials.
            MFARequiredError: MFA step required (contains ``mfa_token``).
        """
        from apps.authn.services.lockout import LockoutService

        # 1. Attempt Django authentication (delegates to backends)
        principal = django_authenticate(
            request,
            username=identifier,
            password=password,
        )

        if principal is None:
            # Try to find the principal for lockout tracking
            _handle_failed_login(
                request=request,
                identifier=identifier,
                reason="invalid_credentials",
            )
            raise InvalidCredentialsError("Invalid credentials")

        # 2. Check lockout
        try:
            LockoutService.check_lockout(principal)
        except AccountLockedError:
            _record_attempt(
                principal=principal,
                request=request,
                identifier=identifier,
                reason="account_locked",
                result=LoginAttemptResult.ACCOUNT_LOCKED,
                auth_method=AuthenticationMethod.PASSWORD,
            )
            raise

        # 3. Check account status
        if not _can_authenticate(principal):
            _record_attempt(
                principal=principal,
                request=request,
                identifier=identifier,
                reason="account_disabled",
                result=LoginAttemptResult.ACCOUNT_DISABLED,
                auth_method=AuthenticationMethod.PASSWORD,
            )
            raise AccountDisabledError("Account is not available")

        # 4. Check MFA
        if _has_mfa(principal):
            mfa_token = _create_mfa_pending(
                principal=principal,
                request=request,
                auth_method=AuthenticationMethod.PASSWORD,
            )

            authn_audit(event_type="MFA_CHALLENGE_ISSUED", principal=principal, request=request)

            raise MFARequiredError(
                mfa_token=mfa_token,
                detail="MFA verification required",
            )

        # 5. Success -- create session
        session, access_token, refresh_token, expires_in = _create_session(
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORD,
        )

        LockoutService.record_success(
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORD,
            identifier=identifier,
        )

        authn_audit(
            event_type="LOGIN_SUCCESS",
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORD,
            session_id=str(getattr(session, "pk", "")),
        )

        logger.info(
            "Password login succeeded for principal %s",
            getattr(principal, "pk", "?"),
        )

        return AuthenticationResult(
            principal=principal,
            session=session,
            auth_method=AuthenticationMethod.PASSWORD,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

    # ── MFA completion ───────────────────────────────────────────────

    @staticmethod
    def complete_mfa_authentication(
        *,
        request: HttpRequest,
        mfa_token: str,
        mfa_code: str,
    ) -> AuthenticationResult:
        """Complete the MFA step of authentication.

        Flow:
        1. Look up and validate the MFA pending record.
        2. Verify the MFA code (TOTP or backup code).
        3. Consume the pending record.
        4. Create session.

        Raises:
            MFAPendingExpiredError: Pending record not found, expired, or consumed.
            MFAVerificationFailedError: MFA code is invalid.
        """
        from apps.authn.services.lockout import LockoutService
        from apps.authn.services.mfa import MFAService

        # 1. Look up pending record
        pending = _resolve_mfa_pending(mfa_token)
        principal = pending.principal

        # 2. Increment attempts
        pending.increment_attempts()

        # 3. Verify MFA code
        mfa_result = MFAService.verify_mfa(principal, mfa_code)

        if not mfa_result.valid:
            if pending.attempts_exceeded:
                pending.consume()  # Invalidate the pending record

                authn_audit(event_type="MFA_FAILED", principal=principal, request=request)

                raise MFAPendingExpiredError("Too many failed MFA attempts. Please log in again.")

            authn_audit(event_type="MFA_FAILED", principal=principal, request=request)
            raise MFAVerificationFailedError("Invalid MFA code")

        # 4. Consume pending
        pending.consume()

        # 5. Map method
        mfa_method = MFAMethod.TOTP
        if mfa_result.method == "backup_code":
            mfa_method = MFAMethod.RECOVERY

        # 6. Create session
        session, access_token, refresh_token, expires_in = _create_session(
            principal=principal,
            request=request,
            auth_method=pending.auth_method or AuthenticationMethod.PASSWORD,
            mfa_method=mfa_method,
        )

        LockoutService.record_success(
            principal=principal,
            request=request,
            auth_method=pending.auth_method or AuthenticationMethod.PASSWORD,
        )

        authn_audit(event_type="MFA_VERIFIED", principal=principal, request=request, mfa_method=mfa_result.method)
        authn_audit(
            event_type="LOGIN_SUCCESS",
            principal=principal,
            request=request,
            auth_method=pending.auth_method or AuthenticationMethod.PASSWORD,
            session_id=str(getattr(session, "pk", "")),
        )

        logger.info(
            "MFA login completed for principal %s (method=%s)",
            getattr(principal, "pk", "?"),
            mfa_result.method,
        )

        return AuthenticationResult(
            principal=principal,
            session=session,
            auth_method=pending.auth_method or AuthenticationMethod.PASSWORD,
            mfa_method=mfa_method,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

    # ── Passwordless login ───────────────────────────────────────────

    @staticmethod
    def request_passwordless_login(
        *,
        principal: object,
        method: str = "email",
    ) -> dict:
        """Request a passwordless login token/OTP.

        Returns a dict with the raw token (and OTP if applicable) for delivery.

        Raises:
            CooldownActiveError: If requested too recently.
        """
        # Check cooldown
        from apps.authn.exceptions import CooldownActiveError
        from apps.authn.models import VerificationToken
        from apps.authn.services.token import TokenService

        cooldown = authn_settings.PASSWORDLESS_RESEND_COOLDOWN_SECONDS
        if cooldown > 0:
            from django.utils import timezone

            cutoff = timezone.now() - timedelta(seconds=cooldown)
            if VerificationToken.objects.filter(
                principal=principal,
                purpose=TokenPurpose.PASSWORDLESS_LOGIN,
                created_at__gte=cutoff,
            ).exists():
                raise CooldownActiveError(
                    retry_after=cooldown,
                    detail="Passwordless login requested too recently",
                )

        generate_otp = method in ("sms", "phone", "email_otp")
        delivery_target = ""
        if method in ("email", "email_otp"):
            delivery_target = getattr(principal, "email", "") or ""
        elif method in ("sms", "phone"):
            delivery_target = getattr(principal, "phone_number", "") or ""

        result = TokenService.create_token(
            principal=principal,
            purpose=TokenPurpose.PASSWORDLESS_LOGIN,
            generate_otp_code=generate_otp,
            otp_length=authn_settings.PASSWORDLESS_OTP_LENGTH,
            ttl_minutes=authn_settings.PASSWORDLESS_TOKEN_TTL_MINUTES,
            max_attempts=authn_settings.PASSWORDLESS_OTP_MAX_ATTEMPTS,
            delivery_target=delivery_target,
        )

        logger.info(
            "Passwordless login requested for principal %s (method=%s)",
            getattr(principal, "pk", "?"),
            method,
        )

        response = {
            "token": result.raw_token,
            "expires_at": result.expires_at,
        }
        if generate_otp and result.raw_otp:
            response["otp"] = result.raw_otp

        return response

    @staticmethod
    def verify_passwordless_login(
        *,
        request: HttpRequest,
        raw_token: str,
        otp: str | None = None,
    ) -> AuthenticationResult:
        """Verify a passwordless login token (magic link or OTP).

        Flow:
        1. Verify the token.
        2. If OTP provided, verify it.
        3. Consume the token.
        4. Check MFA requirement.
        5. Create session.

        Raises:
            TokenInvalidError / TokenExpiredError: Token issues.
            OTPAttemptsExceededError: Too many OTP attempts.
            MFARequiredError: MFA is required after passwordless auth.
        """
        from apps.authn.services.lockout import LockoutService
        from apps.authn.services.token import TokenService

        # 1. Verify token
        token = TokenService.verify_token(raw_token)

        if token.purpose != TokenPurpose.PASSWORDLESS_LOGIN:
            from apps.authn.exceptions import TokenInvalidError

            raise TokenInvalidError("Token is not for passwordless login")

        principal = token.principal

        # 2. If OTP was part of the flow, verify it
        if otp is not None and token.otp_hash:
            TokenService.verify_otp(
                principal=principal,
                purpose=TokenPurpose.PASSWORDLESS_LOGIN,
                otp=otp,
            )

        # 3. Consume token
        TokenService.consume_token(token)

        # 4. Check account status
        if not _can_authenticate(principal):
            raise AccountDisabledError("Account is not available")

        # 5. Check MFA
        if _has_mfa(principal):
            mfa_token = _create_mfa_pending(
                principal=principal,
                request=request,
                auth_method=AuthenticationMethod.PASSWORDLESS,
            )

            authn_audit(event_type="MFA_CHALLENGE_ISSUED", principal=principal, request=request)

            raise MFARequiredError(
                mfa_token=mfa_token,
                detail="MFA verification required",
            )

        # 6. Create session
        session, access_token, refresh_token, expires_in = _create_session(
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORDLESS,
        )

        LockoutService.record_success(
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORDLESS,
        )

        authn_audit(
            event_type="LOGIN_SUCCESS",
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORDLESS,
            session_id=str(getattr(session, "pk", "")),
        )

        logger.info(
            "Passwordless login succeeded for principal %s",
            getattr(principal, "pk", "?"),
        )

        return AuthenticationResult(
            principal=principal,
            session=session,
            auth_method=AuthenticationMethod.PASSWORDLESS,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

    # ── TOTP-only login ──────────────────────────────────────────────

    @staticmethod
    def authenticate_totp_only(
        *,
        request: HttpRequest,
        identifier: str,
        totp_code: str,
    ) -> AuthenticationResult:
        """Authenticate using TOTP code only (no password).

        For users with TOTP as primary auth method. Skips the MFA pending flow.

        Raises:
            InvalidCredentialsError: User not found.
            AccountDisabledError: Account is disabled.
            MFAVerificationFailedError: Invalid TOTP code.
        """
        from django.contrib.auth import get_user_model

        from apps.authn.services.lockout import LockoutService
        from apps.authn.services.mfa import MFAService

        user_model = get_user_model()

        # Resolve principal
        principal = user_model.objects.filter(email=identifier).first()
        if principal is None:
            principal = user_model.objects.filter(username=identifier).first()
        if principal is None:
            raise InvalidCredentialsError("Invalid credentials")

        if not _can_authenticate(principal):
            raise AccountDisabledError("Account is not available")

        LockoutService.check_lockout(principal)

        # Verify TOTP
        mfa_result = MFAService.verify_mfa(principal, totp_code)
        if not mfa_result.valid:
            LockoutService.record_failed_attempt(
                principal=principal,
                identifier=identifier,
                request=request,
                reason="invalid_totp",
                auth_method=AuthenticationMethod.PASSWORDLESS,
            )
            raise MFAVerificationFailedError("Invalid TOTP code")

        session, access_token, refresh_token, expires_in = _create_session(
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORDLESS,
            mfa_method=MFAMethod.TOTP,
        )

        LockoutService.record_success(
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORDLESS,
        )

        authn_audit(
            event_type="LOGIN_SUCCESS",
            principal=principal,
            request=request,
            auth_method=AuthenticationMethod.PASSWORDLESS,
            session_id=str(getattr(session, "pk", "")),
        )

        return AuthenticationResult(
            principal=principal,
            session=session,
            auth_method=AuthenticationMethod.PASSWORDLESS,
            mfa_method=MFAMethod.TOTP,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

    # ── Logout ───────────────────────────────────────────────────────

    @staticmethod
    def logout(
        *,
        request: HttpRequest,
        principal: object,
        session: object | None = None,
        all_sessions: bool = False,
    ) -> None:
        """Log out a principal.

        Args:
            request: The HTTP request.
            principal: The authenticated principal.
            session: The specific session to log out. If None, uses request session.
            all_sessions: If True, terminate all sessions for the principal.
        """
        if all_sessions:
            if hasattr(principal, "terminate_all_sessions"):
                principal.terminate_all_sessions(reason="Principal logged out all sessions")
            else:
                from apps.sessions.models import AuthSession

                AuthSession.objects.terminate_all_for_principal(
                    principal=principal,
                    reason="Principal logged out all sessions",
                )
        elif session is not None:
            if hasattr(session, "logout"):
                session.logout(reason="User logged out")
            elif hasattr(session, "revoke"):
                session.revoke(reason="User logged out")

        authn_audit(event_type="LOGOUT", principal=principal, request=request, all_sessions=all_sessions)

        logger.info(
            "Logout for principal %s (all_sessions=%s)",
            getattr(principal, "pk", "?"),
            all_sessions,
        )


# ── Private helpers ──────────────────────────────────────────────────


def _can_authenticate(principal: object) -> bool:
    """Check if principal can authenticate (active, not deleted, etc.)."""
    # Check can_authenticate property (delegates to principal)
    if hasattr(principal, "can_authenticate"):
        return principal.can_authenticate

    # Fallback: check is_active
    return getattr(principal, "is_active", True)


def _has_mfa(principal: object) -> bool:
    """Check if principal has MFA enabled."""
    return getattr(principal, "has_mfa", False)


def _create_mfa_pending(
    *,
    principal: object,
    request: HttpRequest,
    auth_method: str,
) -> str:
    """Create an MFA pending record and return the raw token."""
    from django.utils import timezone

    raw_token = generate_token()
    token_hash = hmac_hash(raw_token)

    ip_address = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

    # Invalidate existing pending records for this principal
    MFAPendingAuthentication.objects.filter(
        principal=principal,
        consumed_at__isnull=True,
        deleted_at__isnull=True,
    ).delete()

    MFAPendingAuthentication.objects.create(
        principal=principal,
        token_hash=token_hash,
        auth_method=auth_method,
        ip_address=ip_address,
        user_agent=user_agent,
        max_attempts=authn_settings.MFA_PENDING_MAX_ATTEMPTS,
        expires_at=timezone.now() + timedelta(minutes=authn_settings.MFA_PENDING_TTL_MINUTES),
    )

    return raw_token


def _resolve_mfa_pending(mfa_token: str) -> MFAPendingAuthentication:
    """Look up and validate an MFA pending record.

    Raises:
        MFAPendingExpiredError: Record not found, expired, consumed, or attempts exceeded.
    """
    token_hash = hmac_hash(mfa_token)
    pending = (
        MFAPendingAuthentication.objects.select_related("principal")
        .filter(token_hash=token_hash, deleted_at__isnull=True)
        .first()
    )

    if pending is None:
        raise MFAPendingExpiredError("MFA session not found")

    if pending.is_consumed:
        raise MFAPendingExpiredError("MFA session already consumed")

    if pending.is_expired:
        raise MFAPendingExpiredError("MFA session has expired")

    if pending.attempts_exceeded:
        raise MFAPendingExpiredError("Too many MFA attempts")

    return pending


def _create_session(
    *,
    principal: object,
    request: HttpRequest,
    auth_method: str,
    mfa_method: str = MFAMethod.NONE,
) -> tuple[object, str, str, int]:
    """Create an AuthSession and issue JWT access + refresh tokens.

    Returns
    -------
    tuple
        ``(session, access_token, refresh_token, expires_in_seconds)``
    """
    from apps.authn.services.jwt import JWTService
    from apps.authn.settings import authn_settings
    from apps.sessions.models import AuthSession

    ip_address = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

    # Resolve to a Principal instance
    from apps.accounts.models import Principal as PrincipalModel

    if isinstance(principal, PrincipalModel):
        # AUTH_USER_MODEL IS Principal — already correct type
        pass
    elif hasattr(principal, "principal") and principal.principal is not None:
        principal = principal.principal
    elif hasattr(principal, "ensure_principal"):
        principal = principal.ensure_principal(save=True)
    else:
        raise ValueError("Cannot resolve a Principal from the given object; cannot create session")

    # Session TTL matches the refresh token lifetime (30 days default)
    from apps.sessions.enums import SessionChannel

    auth_status = AuthenticationStatus.AUTHENTICATED

    session, _cookie_handle_raw, refresh_token_raw = AuthSession.objects.create_session(
        principal=principal,
        channel=SessionChannel.API,
        auth_method=auth_method,
        auth_status=auth_status,
        mfa_method=mfa_method,
        user_agent=user_agent,
        ip_address=ip_address,
        absolute_ttl=timedelta(days=30),
        refresh_ttl=timedelta(days=30),
        metadata={"device_type": _detect_device_type(user_agent)},
    )

    # Issue JWT access token
    access_token = JWTService.issue_access_token(session)
    expires_in = authn_settings.ACCESS_TOKEN_LIFETIME_SECONDS

    # Store session ID in Django session if using cookies
    if hasattr(request, "session"):
        request.session["user_session_id"] = str(session.pk)

    # Update principal's last login
    if hasattr(principal, "record_successful_login"):
        principal.record_successful_login(ip_address=ip_address, user_agent=user_agent)

    return session, access_token, refresh_token_raw or "", expires_in


def _handle_failed_login(
    *,
    request: HttpRequest,
    identifier: str,
    reason: str,
) -> None:
    """Handle a failed login: find the principal (if any) and record the attempt."""
    from django.contrib.auth import get_user_model

    from apps.authn.services.lockout import LockoutService

    user_model = get_user_model()

    # Try to find the principal for lockout tracking
    principal = user_model.objects.filter(email=identifier).first()
    if principal is None:
        principal = user_model.objects.filter(username=identifier).first()

    LockoutService.record_failed_attempt(
        principal=principal,
        identifier=identifier,
        request=request,
        reason=reason,
        auth_method=AuthenticationMethod.PASSWORD,
    )

    authn_audit(event_type="LOGIN_FAILED", principal=principal, request=request, identifier=identifier, reason=reason)


def _record_attempt(
    *,
    principal: object,
    request: HttpRequest,
    identifier: str,
    reason: str,
    result: str,
    auth_method: str,
) -> None:
    """Record a login attempt."""
    from apps.authn.models import LoginAttempt

    ip_address = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

    LoginAttempt.objects.create(
        principal=principal,
        identifier=identifier,
        result=result,
        auth_method=auth_method,
        ip_address=ip_address,
        user_agent=user_agent,
        failure_reason=reason,
    )


def _get_client_ip(request: HttpRequest) -> str | None:
    """Extract client IP from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _detect_device_type(user_agent: str) -> str:
    """Detect device type from principal agent string."""
    ua_lower = user_agent.lower()
    if "tablet" in ua_lower or "ipad" in ua_lower:
        return "tablet"
    if any(x in ua_lower for x in ["mobile", "android", "iphone"]):
        return "mobile"
    return "desktop"
