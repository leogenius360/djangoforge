"""
Authorization app.

Handles authorization (what can they do):
- Roles/permissions/policies
- ABAC/RBAC engine
- Org/tenant membership if applicable
"""

default_app_config = "apps.authz.apps.AuthzConfig"
