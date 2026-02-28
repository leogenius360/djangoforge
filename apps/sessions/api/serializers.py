"""
Session API serializers.

The login flow now returns tokens directly from ``AuthenticationService``
via ``apps.authn.api.views``.  This module is kept for any session-specific
serialization needs (e.g. listing sessions).
"""
