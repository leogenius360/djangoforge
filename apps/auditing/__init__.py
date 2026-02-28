"""
apps.auditing — Enterprise-grade event-sourcing audit trail for Django.

Primary imports
---------------
``from apps.auditing import audit_registry``
    The global model registry singleton.

``from apps.auditing import audit_settings``
    Typed settings accessor.

``from apps.auditing.models import Event, EventType``
    Core event model and lifecycle enum.

``from apps.auditing.mixins import AuditableModelMixin``
    Model mixin for declarative registration.

``from apps.auditing.context import set_audit_context``
    Context manager for non-HTTP (Celery / management command) code.

``from apps.auditing.services import create_audit_entry``
    Programmatic API for creating audit events.

``from apps.auditing.registry import audit_registry``
    Programmatic model registration / discovery.
"""
