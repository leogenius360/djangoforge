"""Core middleware.

Core should stay small and cross-cutting.

At present the only core-provided middleware is actor tracking, which stamps the
current Principal into a context variable so core model mixins can populate
created_by/updated_by/deleted_by consistently.
"""

import logging

from apps.core.context import set_current_actor

logger = logging.getLogger(__name__)


class ActorTrackingMiddleware:
    """
    Middleware to automatically set the current actor (Principal) for audit tracking.

    This captures the authenticated user's principal and makes it available via
    context variables (ASGI-safe) for automatic population of created_by/updated_by/deleted_by fields.

    Uses the modern __call__ pattern to guarantee cleanup via finally block,
    preventing context leakage in async or exception scenarios.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Process request with guaranteed actor context cleanup."""
        context_manager = None
        try:
            # Set actor context if user is authenticated
            # request.user IS the Principal (AUTH_USER_MODEL), not a model with a .principal FK
            if hasattr(request, "user") and request.user.is_authenticated:
                try:
                    context_manager = set_current_actor(request.user)
                    context_manager.__enter__()
                except Exception as exc:
                    logger.warning("Failed to set actor context: %s", exc, exc_info=True)

            response = self.get_response(request)
            return response
        finally:
            # Guaranteed cleanup even if response raises or middleware short-circuits
            if context_manager is not None:
                try:
                    context_manager.__exit__(None, None, None)
                except Exception as exc:
                    logger.error("Failed to clean up actor context: %s", exc, exc_info=True)
