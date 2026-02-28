"""
Account managers.

Provides ``PrincipalManager`` which doubles as the Django user manager
(required by ``AUTH_USER_MODEL``), enforces soft-delete-aware defaults,
and uses **username** as the canonical identity field.

All principal kinds (user, service, api_client, agent) require a unique
username.  Email is optional and supplemental.
"""

from __future__ import annotations

from django.contrib.auth.models import BaseUserManager

from apps.core.context import set_current_actor

from .querysets import PrincipalQuerySet


class PrincipalManager(BaseUserManager.from_queryset(PrincipalQuerySet)):  # type: ignore[misc]
    """Manager for Principal (AUTH_USER_MODEL).

    Implements Django's ``create_user`` / ``create_superuser`` contract
    using **username** as the required identifier (not email).

    Default queryset excludes soft-deleted rows via ``active()``.
    """

    use_in_migrations = True

    def get_queryset(self) -> PrincipalQuerySet:
        """Default: exclude soft-deleted rows."""
        return super().get_queryset().active()

    def with_deleted(self) -> PrincipalQuerySet:
        """Return queryset including soft-deleted rows."""
        return super().get_queryset()

    def deleted(self) -> PrincipalQuerySet:
        """Return only soft-deleted rows."""
        return self.with_deleted().deleted()

    # ------------------------------------------------------------------
    # Username normalisation
    # ------------------------------------------------------------------

    @classmethod
    def normalize_username(cls, username: str) -> str:
        """Normalize the username.

        Strips whitespace and lowercases if ``USERNAME_CASE_INSENSITIVE``
        is enabled in accounts settings.
        """
        from apps.accounts.settings import accounts_settings

        username = username.strip()
        if accounts_settings.USERNAME_CASE_INSENSITIVE:
            username = username.lower()
        return username

    @staticmethod
    def normalize_phone_number(phone_number: str) -> str:
        """Normalize a phone number to E.164 format using ``phonenumbers``.

        Strips whitespace then attempts to parse and reformat the number.
        Returns the E.164 string on success, or the stripped raw value if
        parsing fails (field-level validation will reject it later).
        """
        import phonenumbers

        phone_number = phone_number.strip()
        try:
            parsed = phonenumbers.parse(phone_number, None)
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            return phone_number

    # ------------------------------------------------------------------
    # Core creation
    # ------------------------------------------------------------------

    def _create_principal(self, username: str, password: str | None = None, kind: str = "user", **extra_fields):
        """Create and persist a Principal with the given username, password, and kind."""
        if not username:
            raise ValueError("All principals must have a username.")

        username = self.normalize_username(username)

        # Normalize email if provided
        email = extra_fields.pop("email", None)
        if email:
            email = self.normalize_email(email)

        # Normalize phone number if provided
        phone_number = extra_fields.pop("phone_number", None)
        phone_number = self.normalize_phone_number(phone_number) if phone_number else ""

        principal = self.model(
            username=username,
            email=email,
            phone_number=phone_number,
            kind=kind,
            **extra_fields,
        )

        if password:
            principal.set_password(password)
        else:
            principal.set_unusable_password()

        # Bootstrap: the principal stamps itself as its own creator.
        # UUID pk is pre-populated (default=uuid.uuid4) so no DB row is needed yet.
        with set_current_actor(principal):
            principal.save(using=self._db)
        return principal

    # ------------------------------------------------------------------
    # Django auth contract
    # ------------------------------------------------------------------

    def create_user(self, username: str, password: str | None = None, **extra_fields):
        """Create a regular user principal.

        Parameters
        ----------
        username : str
            Required unique identifier.
        password : str, optional
            Raw password (will be hashed).
        **extra_fields
            Additional fields such as ``email``, ``display_name``, etc.
        """
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("kind", "user")
        return self._create_principal(username, password, **extra_fields)

    def create_superuser(self, username: str, password: str | None = None, **extra_fields):
        """Create a superuser principal.

        Enforces ``is_staff=True`` and ``is_superuser=True``.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("kind", "user")
        extra_fields.setdefault("passwordless_enabled", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_principal(username, password, **extra_fields)

    def get_by_natural_key(self, username: str):
        """Look up by username (case-insensitive)."""
        return self.get(username__iexact=username)

    # ------------------------------------------------------------------
    # Kind-specific factories
    # ------------------------------------------------------------------

    def create_service_principal(self, username: str, display_name: str = "", **extra_fields):
        """Create a service-type principal (no password)."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("passwordless_enabled", True)
        return self._create_principal(
            username, password=None, kind="service", display_name=display_name, **extra_fields
        )

    def create_api_client_principal(self, username: str, display_name: str = "", **extra_fields):
        """Create an api_client-type principal (no password)."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("passwordless_enabled", True)
        return self._create_principal(
            username, password=None, kind="api_client", display_name=display_name, **extra_fields
        )

    def create_agent_principal(self, username: str, display_name: str = "", **extra_fields):
        """Create an agent-type principal (no password)."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("passwordless_enabled", True)
        return self._create_principal(username, password=None, kind="agent", display_name=display_name, **extra_fields)
