"""
Pure Django API views for the DjangoForge API layer.

Provides ``ForgeAPIView`` and generic view classes (``ListCreateAPIView``,
``RetrieveUpdateDestroyAPIView``, etc.) that replace DRF generic views.

All views:
- Parse JSON request bodies automatically.
- Run authentication backends and set ``request.user`` / ``request.auth``.
- Check permission classes.
- Handle ``APIException`` subclasses and return structured JSON errors.
- Return ``django.http.JsonResponse`` instances.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.core.api import exceptions, status
from apps.core.api.pagination import PageNumberPagination
from apps.core.api.permissions import AllowAny, IsAuthenticated

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response helper
# ---------------------------------------------------------------------------


def api_response(data: Any = None, status: int = 200, headers: dict | None = None) -> JsonResponse:
    """Create a ``JsonResponse`` with optional headers."""
    if data is None:
        data = {}
    response = JsonResponse(data, status=status, safe=False)
    if headers:
        for key, value in headers.items():
            response[key] = value
    return response


# Alias for DRF-style ``Response`` usage
Response = api_response


# ---------------------------------------------------------------------------
# ForgeAPIView
# ---------------------------------------------------------------------------


@method_decorator(csrf_exempt, name="dispatch")
class ForgeAPIView(View):
    """
    Base API view that provides DRF-like behaviour on top of Django's ``View``.

    Features:
    - JSON request body parsing (``request.data``)
    - Authentication via pluggable backends
    - Permission checking
    - Exception handling with structured JSON responses
    """

    permission_classes: list[type] = [IsAuthenticated]
    authentication_classes: list[type] | None = None

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        # Parse JSON body
        self._parse_request_data(request)

        # Run authentication
        try:
            self._perform_authentication(request)
        except exceptions.APIException as exc:
            return self._handle_exception(exc, request)

        # Check permissions
        try:
            self._check_permissions(request)
        except exceptions.APIException as exc:
            return self._handle_exception(exc, request)

        # Dispatch to the handler
        try:
            response = super().dispatch(request, *args, **kwargs)
            if isinstance(response, JsonResponse):
                return response
            return response
        except exceptions.APIException as exc:
            return self._handle_exception(exc, request)
        except Exception as exc:
            # Try custom exception handler before returning 500
            result = self._try_custom_exception_handler(exc, request)
            if result is not None:
                return result
            logger.exception("Unhandled exception in %s", self.__class__.__name__)
            return api_response({"detail": "Internal server error."}, status=500)

    def _parse_request_data(self, request: HttpRequest) -> None:
        """Attach parsed JSON body as ``request.data``."""
        request.data = {}  # type: ignore[attr-defined]
        if request.method in ("POST", "PUT", "PATCH") and request.body:
            content_type = request.content_type or ""
            if "json" in content_type or "application/json" in content_type:
                try:
                    request.data = json.loads(request.body)  # type: ignore[attr-defined]
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            elif not content_type or content_type == "application/octet-stream":
                # Try JSON anyway for convenience
                try:
                    request.data = json.loads(request.body)  # type: ignore[attr-defined]
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

    def _get_authentication_classes(self) -> list:
        """Return authentication backends to use for this view."""
        if self.authentication_classes is not None:
            return [cls() for cls in self.authentication_classes]

        # Default: load from settings
        from apps.core.api.authentication import BaseAuthentication

        default_classes = getattr(settings, "FORGE_AUTHENTICATION_CLASSES", [])
        backends = []
        for cls_path in default_classes:
            if isinstance(cls_path, str):
                module_path, cls_name = cls_path.rsplit(".", 1)
                import importlib

                module = importlib.import_module(module_path)
                cls = getattr(module, cls_name)
            else:
                cls = cls_path
            if isinstance(cls, type) and issubclass(cls, BaseAuthentication):
                backends.append(cls())
            elif callable(cls):
                backends.append(cls())
        return backends

    def _perform_authentication(self, request: HttpRequest) -> None:
        """Authenticate the request using configured backends."""
        # Check if this view allows any access
        for perm_class in self.permission_classes:
            if perm_class is AllowAny or (isinstance(perm_class, type) and issubclass(perm_class, AllowAny)):
                # AllowAny — still try auth but don't fail if none succeeds
                for backend in self._get_authentication_classes():
                    result = backend.authenticate(request)
                    if result is not None:
                        request.user, request.auth = result  # type: ignore[attr-defined]
                        return
                return

        for backend in self._get_authentication_classes():
            try:
                result = backend.authenticate(request)
            except exceptions.AuthenticationFailed:
                raise
            if result is not None:
                request.user, request.auth = result  # type: ignore[attr-defined]
                return

    def _check_permissions(self, request: HttpRequest) -> None:
        """Check all permission classes."""
        for perm_class in self.permission_classes:
            permission = perm_class() if isinstance(perm_class, type) else perm_class
            if not permission.has_permission(request, self):
                raise exceptions.PermissionDenied()

    def check_object_permissions(self, request: HttpRequest, obj: Any) -> None:
        """Check object-level permissions."""
        for perm_class in self.permission_classes:
            permission = perm_class() if isinstance(perm_class, type) else perm_class
            if not permission.has_object_permission(request, self, obj):
                raise exceptions.PermissionDenied()

    def _try_custom_exception_handler(self, exc: Exception, request: HttpRequest) -> JsonResponse | None:
        """Try custom exception handler for non-APIException errors."""
        handler = getattr(settings, "FORGE_EXCEPTION_HANDLER", None)
        if handler:
            if isinstance(handler, str):
                import importlib

                module_path, func_name = handler.rsplit(".", 1)
                module = importlib.import_module(module_path)
                handler = getattr(module, func_name)
            return handler(exc, {"request": request, "view": self})
        return None

    def _handle_exception(self, exc: exceptions.APIException, request: HttpRequest) -> JsonResponse:
        """Convert API exceptions to JSON responses."""
        # Check for custom exception handler
        handler = getattr(settings, "FORGE_EXCEPTION_HANDLER", None)
        if handler:
            if isinstance(handler, str):
                import importlib

                module_path, func_name = handler.rsplit(".", 1)
                module = importlib.import_module(module_path)
                handler = getattr(module, func_name)
            result = handler(exc, {"request": request, "view": self})
            if result is not None:
                return result

        data: dict[str, Any] = {"detail": str(exc.detail)}
        if isinstance(exc, exceptions.ValidationError) and isinstance(exc.detail, dict):
            data = exc.detail
        headers = {}
        if isinstance(exc, exceptions.AuthenticationFailed):
            headers["WWW-Authenticate"] = 'Bearer realm="api"'
        return api_response(data, status=exc.status_code, headers=headers)

    def http_method_not_allowed(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return api_response(
            {"detail": f'Method "{request.method}" not allowed.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


# Shortcut for backwards compat
APIView = ForgeAPIView


# ---------------------------------------------------------------------------
# Generic views
# ---------------------------------------------------------------------------


class GenericAPIView(ForgeAPIView):
    """
    Base class for generic views that operate on querysets.
    """

    queryset = None
    serializer_class = None
    lookup_field: str = "pk"
    lookup_url_kwarg: str | None = None
    pagination_class: type | None = None
    filter_backends: list[type] = []

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset.all()
        msg = f"'{self.__class__.__name__}' should either include a `queryset` attribute, or override the `get_queryset()` method."
        raise AssertionError(msg)

    def get_object(self):
        queryset = self.get_queryset()
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)
        if lookup_value is None:
            raise exceptions.NotFound()
        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except queryset.model.DoesNotExist as e:
            raise exceptions.NotFound() from e
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_class(self):
        if self.serializer_class is not None:
            return self.serializer_class
        msg = f"'{self.__class__.__name__}' should either include a `serializer_class` attribute, or override `get_serializer_class()`."
        raise AssertionError(msg)

    def get_serializer(self, *args, **kwargs):
        cls = self.get_serializer_class()
        kwargs.setdefault("context", self.get_serializer_context())
        return cls(*args, **kwargs)

    def get_serializer_context(self) -> dict:
        return {"request": self.request, "view": self}

    def filter_queryset(self, queryset):
        for backend_class in self.filter_backends:
            backend = backend_class()
            queryset = backend.filter_queryset(self.request, queryset, self)
        return queryset

    def paginate_queryset(self, queryset):
        if self.pagination_class is None:
            return None
        self.paginator = self.pagination_class()
        return self.paginator.paginate_queryset(queryset, self.request)

    def get_paginated_response(self, data):
        return api_response(self.paginator.get_paginated_response_data(data))

    def get_permissions(self):
        """Return instantiated permission objects. Override for dynamic permissions."""
        return [perm() if isinstance(perm, type) else perm for perm in self.permission_classes]


# ---------------------------------------------------------------------------
# Mixin classes
# ---------------------------------------------------------------------------


class ListMixin:
    """Provides ``list()`` action for GET requests on a collection."""

    def list(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(instance=page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(instance=queryset, many=True)
        return api_response(serializer.data)


class CreateMixin:
    """Provides ``create()`` action for POST requests."""

    def create(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return api_response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer) -> None:
        serializer.save()


class RetrieveMixin:
    """Provides ``retrieve()`` action for GET on a single object."""

    def retrieve(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        instance = self.get_object()
        serializer = self.get_serializer(instance=instance)
        return api_response(serializer.data)


class UpdateMixin:
    """Provides ``update()`` action for PUT/PATCH requests."""

    def update(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        instance = self.get_object()
        partial = request.method == "PATCH"
        serializer = self.get_serializer(instance=instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return api_response(serializer.data)

    def perform_update(self, serializer) -> None:
        serializer.save()


class DestroyMixin:
    """Provides ``destroy()`` action for DELETE requests."""

    def destroy(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance) -> None:
        instance.delete()


# ---------------------------------------------------------------------------
# Concrete generic views
# ---------------------------------------------------------------------------


class ListAPIView(ListMixin, GenericAPIView):
    """Read-only list endpoint."""

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.list(request, *args, **kwargs)


class CreateAPIView(CreateMixin, GenericAPIView):
    """Create-only endpoint."""

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.create(request, *args, **kwargs)


class ListCreateAPIView(ListMixin, CreateMixin, GenericAPIView):
    """List and create endpoint."""

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.list(request, *args, **kwargs)

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.create(request, *args, **kwargs)


class RetrieveAPIView(RetrieveMixin, GenericAPIView):
    """Single-object read-only endpoint."""

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.retrieve(request, *args, **kwargs)


class RetrieveUpdateAPIView(RetrieveMixin, UpdateMixin, GenericAPIView):
    """Single-object read + update endpoint."""

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.retrieve(request, *args, **kwargs)

    def put(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.update(request, *args, **kwargs)

    def patch(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.update(request, *args, **kwargs)


class RetrieveDestroyAPIView(RetrieveMixin, DestroyMixin, GenericAPIView):
    """Single-object read + delete endpoint."""

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.retrieve(request, *args, **kwargs)

    def delete(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.destroy(request, *args, **kwargs)


class RetrieveUpdateDestroyAPIView(RetrieveMixin, UpdateMixin, DestroyMixin, GenericAPIView):
    """Single-object read + update + delete endpoint."""

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.retrieve(request, *args, **kwargs)

    def put(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.update(request, *args, **kwargs)

    def patch(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.update(request, *args, **kwargs)

    def delete(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self.destroy(request, *args, **kwargs)
