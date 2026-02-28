"""
API package for the accounts app.

Exposes CRUD endpoints for the concrete principal subtypes:
UserAccount, ServiceAccount, APIClient, AgentAccount.

Principal itself is NOT exposed as a public API resource.
Authentication workflows (login, registration, MFA, etc.) belong in the authn app.
Session management belongs in the sessions app.
Profile management belongs in the profiles app.
"""
