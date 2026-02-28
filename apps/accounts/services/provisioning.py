"""
Atomic provisioning service for accounts.

``AccountProvisioner`` encapsulates the transactional creation and teardown of
Principal + concrete account pairs.  This replaces scattered signal-based
creation with explicit, auditable, transactional operations.

Usage::

    from apps.accounts.services import AccountProvisioner

    provisioner = AccountProvisioner()
    principal, user = provisioner.provision_user(
        username="jdoe",
        password="s3cret!",
        email="jdoe@example.com",
        display_name="Jane Doe",
    )

Design notes
------------
- Every ``provision_*`` method runs inside ``transaction.atomic()``.
- Principal is always created first, then the concrete account.
- ``sync_display_name()`` is called explicitly after creation.
- ``deprovision()`` soft-deletes both the concrete account and the principal
  atomically, bumping the security stamp to invalidate all sessions.

Compliance alignment
--------------------
- ISO 27001 A.9.2 -- user access provisioning
- SOC 2 CC6.2     -- provisioning logical access
- NIST 800-63B    -- identity proofing and lifecycle
"""

from __future__ import annotations

import logging
import secrets
import string
from typing import Any

from django.db import transaction

from apps.accounts.constants import (
    USERNAME_PREFIX_AGENT,
    USERNAME_PREFIX_API_CLIENT,
    USERNAME_PREFIX_SERVICE,
)
from apps.accounts.enums import PrincipalKind
from apps.accounts.exceptions import ProvisioningError, UsernameConflictError
from apps.accounts.models.agent import AgentAccount
from apps.accounts.models.api_client import APIClient
from apps.accounts.models.principal import Principal
from apps.accounts.models.service_account import ServiceAccount
from apps.accounts.models.user import UserAccount
from apps.accounts.settings import accounts_settings

logger = logging.getLogger(__name__)


class AccountProvisioner:
    """Atomic provisioning and deprovisioning of accounts.

    All methods are idempotent-safe: they raise ``ProvisioningError`` on
    conflict rather than creating duplicates.
    """

    # ------------------------------------------------------------------
    # User provisioning
    # ------------------------------------------------------------------

    def provision_user(
        self,
        username: str,
        password: str | None = None,
        *,
        email: str | None = None,
        display_name: str = "",
        phone_number: str | None = None,
        **extra_principal_fields: Any,
    ) -> tuple[Principal, UserAccount]:
        """Create a Principal (kind=user) and linked UserAccount atomically.

        Parameters
        ----------
        username : str
            Required unique username.
        password : str, optional
            Raw password (hashed by Django).
        email : str, optional
            Email address stored on Principal.
        display_name : str
            Human-readable display name (stored on Principal).
        phone_number : str, optional
            E.164 phone number (stored on Principal).
        **extra_principal_fields
            Additional fields passed to Principal creation.

        Returns
        -------
        tuple[Principal, UserAccount]
            The created principal and user account.

        Raises
        ------
        UsernameConflictError
            If the username is already taken.
        ProvisioningError
            If creation fails for any other reason.
        """
        try:
            with transaction.atomic():
                self._check_username_available(username)

                principal = Principal.objects.create_user(
                    username=username,
                    password=password,
                    email=email,
                    display_name=display_name,
                    phone_number=phone_number or "",
                    **extra_principal_fields,
                )

                user_account = UserAccount.objects.create(
                    principal=principal,
                )

                logger.info("Provisioned user account: %s (principal=%s)", username, principal.pk)
                return principal, user_account

        except UsernameConflictError:
            raise
        except Exception as exc:
            raise ProvisioningError(f"Failed to provision user '{username}': {exc}") from exc

    # ------------------------------------------------------------------
    # Service account provisioning
    # ------------------------------------------------------------------

    def provision_service_account(
        self,
        username: str | None = None,
        *,
        service_name: str,
        name: str = "",
        description: str = "",
        owner: Principal | None = None,
        allowed_scopes: list[str] | None = None,
        **extra_principal_fields: Any,
    ) -> tuple[Principal, ServiceAccount]:
        """Create a Principal (kind=service) and linked ServiceAccount atomically.

        Parameters
        ----------
        username : str, optional
            If not provided and ``AUTO_GENERATE_SERVICE_USERNAME`` is True,
            a username is generated from the service_name.
        service_name : str
            Logical service name (e.g., "payment-gateway").
        name : str
            Human-readable name (defaults to service_name).
        description : str
            Free-text description.
        owner : Principal, optional
            User principal who owns this service account.
        allowed_scopes : list[str], optional
            OAuth/authorization scopes.
        **extra_principal_fields
            Additional fields passed to Principal creation.

        Returns
        -------
        tuple[Principal, ServiceAccount]

        Raises
        ------
        UsernameConflictError
            If the username is already taken.
        ProvisioningError
            If creation fails.
        """
        if not username:
            if accounts_settings.AUTO_GENERATE_SERVICE_USERNAME:
                username = self.generate_username(PrincipalKind.SERVICE, service_name)
            else:
                raise ProvisioningError("Username is required for service account provisioning.")

        if not name:
            name = service_name

        try:
            with transaction.atomic():
                self._check_username_available(username)

                principal = Principal.objects.create_service_principal(
                    username=username,
                    display_name=service_name,
                    **extra_principal_fields,
                )

                service_account = ServiceAccount.objects.create(
                    principal=principal,
                    name=name,
                    service_name=service_name,
                    description=description,
                    owner=owner,
                    allowed_scopes=allowed_scopes or [],
                )

                service_account.sync_display_name()

                logger.info("Provisioned service account: %s (principal=%s)", service_name, principal.pk)
                return principal, service_account

        except UsernameConflictError:
            raise
        except Exception as exc:
            raise ProvisioningError(f"Failed to provision service account '{service_name}': {exc}") from exc

    # ------------------------------------------------------------------
    # API client provisioning
    # ------------------------------------------------------------------

    def provision_api_client(
        self,
        username: str | None = None,
        *,
        client_id: str,
        client_type: str = "confidential",
        owner: Principal | None = None,
        redirect_uris: list[str] | None = None,
        allowed_scopes: list[str] | None = None,
        grant_types: list[str] | None = None,
        website_url: str = "",
        terms_url: str = "",
        privacy_url: str = "",
        **extra_principal_fields: Any,
    ) -> tuple[Principal, APIClient, str | None]:
        """Create a Principal (kind=api_client) and linked APIClient atomically.

        For **confidential** clients, a random secret is generated, hashed,
        and stored.  The plaintext secret is returned exactly once.

        Parameters
        ----------
        username : str, optional
            If not provided, auto-generated from client_id.
        client_id : str
            Unique public client identifier.
        client_type : str
            "confidential" or "public".
        owner : Principal, optional
            User principal who owns this API client.
        redirect_uris / allowed_scopes / grant_types : list[str], optional
            OAuth configuration.
        **extra_principal_fields
            Additional fields passed to Principal creation.

        Returns
        -------
        tuple[Principal, APIClient, str | None]
            The created principal, API client, and plaintext secret (or None
            for public clients).

        Raises
        ------
        UsernameConflictError
            If the username is already taken.
        ProvisioningError
            If creation fails.
        """
        if not username:
            username = self.generate_username(PrincipalKind.API_CLIENT, client_id)

        plaintext_secret: str | None = None
        hashed_secret = ""

        if client_type == "confidential":
            plaintext_secret = self._generate_client_secret()
            from django.contrib.auth.hashers import make_password

            hashed_secret = make_password(plaintext_secret)

        try:
            with transaction.atomic():
                self._check_username_available(username)

                principal = Principal.objects.create_api_client_principal(
                    username=username,
                    display_name=client_id,
                    **extra_principal_fields,
                )

                api_client = APIClient.objects.create(
                    principal=principal,
                    client_id=client_id,
                    client_secret=hashed_secret,
                    client_type=client_type,
                    redirect_uris=redirect_uris or [],
                    allowed_scopes=allowed_scopes or [],
                    grant_types=grant_types or [],
                    owner=owner,
                    website_url=website_url,
                    terms_url=terms_url,
                    privacy_url=privacy_url,
                )

                api_client.sync_display_name()

                logger.info("Provisioned API client: %s (principal=%s)", client_id, principal.pk)
                return principal, api_client, plaintext_secret

        except UsernameConflictError:
            raise
        except Exception as exc:
            raise ProvisioningError(f"Failed to provision API client '{client_id}': {exc}") from exc

    # ------------------------------------------------------------------
    # Agent provisioning
    # ------------------------------------------------------------------

    def provision_agent(
        self,
        username: str | None = None,
        *,
        identifier: str,
        agent_type: str,
        description: str = "",
        owner: Principal | None = None,
        allowed_scopes: list[str] | None = None,
        capabilities: dict[str, Any] | None = None,
        **extra_principal_fields: Any,
    ) -> tuple[Principal, AgentAccount]:
        """Create a Principal (kind=agent) and linked AgentAccount atomically.

        Parameters
        ----------
        username : str, optional
            If not provided, auto-generated from identifier.
        identifier : str
            Unique machine-readable agent identifier.
        agent_type : str
            Agent classification (e.g., "llm", "workflow", "cron").
        description : str
            Free-text description.
        owner : Principal, optional
            User principal who owns this agent.
        allowed_scopes : list[str], optional
            OAuth/authorization scopes.
        capabilities : dict, optional
            JSON capability flags.
        **extra_principal_fields
            Additional fields passed to Principal creation.

        Returns
        -------
        tuple[Principal, AgentAccount]

        Raises
        ------
        UsernameConflictError
            If the username is already taken.
        ProvisioningError
            If creation fails.
        """
        if not username:
            username = self.generate_username(PrincipalKind.AGENT, identifier)

        try:
            with transaction.atomic():
                self._check_username_available(username)

                principal = Principal.objects.create_agent_principal(
                    username=username,
                    display_name=identifier,
                    **extra_principal_fields,
                )

                agent_account = AgentAccount.objects.create(
                    principal=principal,
                    identifier=identifier,
                    agent_type=agent_type,
                    description=description,
                    owner=owner,
                    allowed_scopes=allowed_scopes or [],
                    capabilities=capabilities or {},
                )

                agent_account.sync_display_name()

                logger.info("Provisioned agent account: %s (principal=%s)", identifier, principal.pk)
                return principal, agent_account

        except UsernameConflictError:
            raise
        except Exception as exc:
            raise ProvisioningError(f"Failed to provision agent '{identifier}': {exc}") from exc

    # ------------------------------------------------------------------
    # Deprovisioning
    # ------------------------------------------------------------------

    def deprovision(self, principal: Principal) -> None:
        """Soft-delete a principal and its concrete account atomically.

        Bumps the security stamp to invalidate all active sessions.

        Parameters
        ----------
        principal : Principal
            The principal to deprovision.

        Raises
        ------
        ProvisioningError
            If deprovisioning fails.
        """
        try:
            with transaction.atomic():
                # Soft-delete concrete account if it exists
                concrete = self._get_concrete_account(principal)
                if concrete and not getattr(concrete, "deleted_at", None):
                    concrete.soft_delete()

                # Soft-delete principal (also bumps security stamp)
                # May be a no-op if concrete.soft_delete() already handled it
                if not principal.deleted_at:
                    principal.soft_delete()

                logger.info("Deprovisioned principal: %s (pk=%s)", principal.username, principal.pk)

        except Exception as exc:
            raise ProvisioningError(f"Failed to deprovision principal '{principal.username}': {exc}") from exc

    # ------------------------------------------------------------------
    # Username generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_username(kind: str, identifier: str) -> str:
        """Generate a prefixed username for non-user principal kinds.

        Format: ``{prefix}-{sanitized_identifier}``

        Parameters
        ----------
        kind : str
            Principal kind (from ``PrincipalKind``).
        identifier : str
            Base identifier to derive the username from.

        Returns
        -------
        str
            Generated username.
        """
        prefix_map = {
            PrincipalKind.SERVICE: USERNAME_PREFIX_SERVICE,
            PrincipalKind.API_CLIENT: USERNAME_PREFIX_API_CLIENT,
            PrincipalKind.AGENT: USERNAME_PREFIX_AGENT,
        }

        prefix = prefix_map.get(kind, kind)

        # Sanitize: lowercase, replace spaces/special chars with hyphens
        sanitized = identifier.lower().strip()
        sanitized = "".join(c if c.isalnum() or c in "-_." else "-" for c in sanitized)
        sanitized = sanitized.strip("-_.")

        username = f"{prefix}-{sanitized}" if sanitized else prefix
        return username[:150]  # Respect max length

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_username_available(username: str) -> None:
        """Raise ``UsernameConflictError`` if the username is taken."""
        if Principal.objects.with_deleted().filter(username__iexact=username).exists():
            raise UsernameConflictError(
                f"Username '{username}' is already in use.",
                username=username,
            )

    @staticmethod
    def _generate_client_secret() -> str:
        """Generate a cryptographically secure client secret."""
        length = max(accounts_settings.API_CLIENT_SECRET_MIN_LENGTH, 32)
        alphabet = string.ascii_letters + string.digits + "-_"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def _get_concrete_account(principal: Principal):
        """Return the concrete account linked to the principal, or None."""
        kind_to_attr = {
            PrincipalKind.USER: "user_account",
            PrincipalKind.SERVICE: "service_account",
            PrincipalKind.API_CLIENT: "api_client",
            PrincipalKind.AGENT: "agent_account",
        }
        attr = kind_to_attr.get(principal.kind)
        if not attr:
            return None
        try:
            return getattr(principal, attr)
        except Exception:
            return None
