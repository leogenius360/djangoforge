"""
OpenAPI authentication extensions for our custom auth classes.

Registers ``OpenApiAuthenticationExtension`` sub-classes so that
Swagger UI shows the correct ``Authorization: Bearer <jwt>`` security
scheme and the "Authorize" button works out of the box.

Loaded via ``SessionsConfig.ready()`` in ``apps.py``.
"""

from apps.core.api.decorators import OpenApiAuthenticationExtension


class SessionJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Maps ``SessionJWTAuthentication`` → HTTP Bearer (JWT)."""

    target_class = "apps.sessions.authentication.SessionJWTAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT access token issued by ``POST /api/auth/login/``.\n\n"
                "Paste the ``access_token`` value from the login response."
            ),
        }


class DualAuthenticationScheme(OpenApiAuthenticationExtension):
    """Maps ``DualAuthentication`` → HTTP Bearer (JWT)."""

    target_class = "apps.sessions.authentication.DualAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT access token issued by ``POST /api/auth/login/``.\n\n"
                "Paste the ``access_token`` value from the login response."
            ),
        }
