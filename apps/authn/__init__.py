"""
Authentication app.

Handles authentication flows including:
- MFA credentials (TOTP/WebAuthn/recovery)
- Login flows, step-up auth decisions
- Password policies, verification, challenges
"""

default_app_config = "apps.authn.apps.AuthnConfig"
