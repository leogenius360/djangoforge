"""
Custom session backend using AuthSession model.

Replaces Django's default session backend to use our enterprise AuthSession model.
"""

from django.contrib.sessions.backends.base import CreateError, SessionBase
from django.utils import timezone

from apps.core.context import require_system_actor
from apps.sessions.models import AuthSession


class DatabaseSessionBackend(SessionBase):
    """
    Session backend that uses the AuthSession model.

    This replaces Django's default session backend with our custom
    enterprise session management system.
    """

    def __init__(self, session_key=None):
        super().__init__(session_key)
        self._session_obj = None

    def load(self):
        """Load session data from database."""
        if self.session_key is None:
            return {}

        try:
            session = AuthSession.objects.get(
                pk=self.session_key,
                deleted_at__isnull=True,
                disabled_at__isnull=True,
            )

            # Check if session is valid (includes auth_status check from metadata)
            if not session.is_valid:
                self.delete()
                return {}

            self._session_obj = session

            # Decode session data if it exists
            session_data = session.metadata.get("session_data", "")
            if session_data:
                return self.decode(session_data)
            return {}
        except AuthSession.DoesNotExist:
            self._session_key = None
            return {}

    def create(self):
        """Create a new session."""
        # Generate a new session key
        while True:
            self._session_key = self._get_new_session_key()
            try:
                self.save(must_create=True)
            except CreateError:
                continue
            self.modified = True
            return

    def save(self, must_create=False):
        """Save session data to database."""
        if self.session_key is None:
            return self.create()

        data = self._get_session(no_load=must_create)
        encoded_data = self.encode(data)

        if must_create:
            # Creating new session - will be populated by middleware/auth backend
            # For now, create a minimal session object
            raise CreateError("Session creation handled by authentication backend")

        # Update existing session
        if self._session_obj:
            self._session_obj.metadata["session_data"] = encoded_data
            self._session_obj.save(update_fields=["metadata"])

    def exists(self, session_key):
        """Check if session exists and is valid."""
        # Only filter by status at DB level; auth_status is in metadata
        try:
            session = AuthSession.objects.get(
                pk=session_key,
                deleted_at__isnull=True,
                disabled_at__isnull=True,
            )
            return session.is_valid
        except AuthSession.DoesNotExist:
            return False

    def delete(self, session_key=None):
        """Delete a session."""
        if session_key is None:
            if self.session_key is None:
                return
            session_key = self.session_key

        try:
            session = AuthSession.objects.get(pk=session_key)
            session.logout(reason="Session deleted")
        except AuthSession.DoesNotExist:
            pass

    @classmethod
    def clear_expired(cls):
        """Clear all expired sessions."""
        now = timezone.now()
        system_actor = require_system_actor()
        # Mark sessions as expired if their expiry time has passed
        AuthSession.objects.filter(
            disabled_at__isnull=True,
            deleted_at__isnull=True,
            expires_at__lte=now,
        ).update(
            disabled_at=now,
            disabled_by=system_actor,
            disabled_reason="Session expired (cleanup)",
        )
