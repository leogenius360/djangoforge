"""
Tests for Forge auth policy.
"""

from djangoforge.auth.policy import ForgeAuthPolicy, Principal


class TestForgeAuthPolicy:
    def test_authenticate_with_headers(self):
        policy = ForgeAuthPolicy()
        meta = {
            "HTTP_X_USER_ID": "user-42",
            "HTTP_X_EMAIL": "test@example.com",
            "HTTP_X_TENANT": "acme",
            "HTTP_X_GROUPS": "admin,editor",
            "HTTP_X_SCOPES": "read,write",
            "HTTP_X_AUTH_PROVIDER": "okta",
        }
        ctx = policy.authenticate(meta)
        assert ctx is not None
        assert ctx.user_id == "user-42"
        assert ctx.email == "test@example.com"
        assert ctx.tenant == "acme"
        assert ctx.groups == ["admin", "editor"]
        assert ctx.scopes == ["read", "write"]
        assert ctx.auth_provider == "okta"

    def test_returns_none_without_user_id(self):
        policy = ForgeAuthPolicy()
        ctx = policy.authenticate({"HTTP_X_EMAIL": "a@b.com"})
        assert ctx is None

    def test_to_principal(self):
        policy = ForgeAuthPolicy()
        ctx = policy.authenticate({"HTTP_X_USER_ID": "u1", "HTTP_X_TENANT": "t1"})
        assert ctx is not None
        principal = policy.to_principal(ctx)
        assert isinstance(principal, Principal)
        assert principal.subject == "u1"
        assert principal.tenant == "t1"
