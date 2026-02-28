"""
Reusable hardened settings base class.

This module provides a ``BaseSettings`` class that any Django app can subclass
to implement a validated, immutable, namespace-based configuration pattern.

Features
--------
- Fully typed settings interface (IDE autocomplete + mypy-friendly)
- Runtime type validation (fail fast on misconfiguration)
- Immutable settings object at runtime (prevents accidental mutation)
- Efficient attribute access (values are set as real attributes)
- Automatic reload on ``setting_changed`` signal (test-friendly)

Usage
-----
::

    from apps.core.settings import BaseSettings

    class MyAppSettings(BaseSettings):
        settings_key = "MY_APP"
        FOO: str = "default"
        BAR: int = 42

    my_settings = MyAppSettings()
"""

from __future__ import annotations

from copy import deepcopy
from types import UnionType
from typing import Any, ClassVar, TypeVar, Union, cast, get_args, get_origin, overload

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured

T = TypeVar("T")


def _is_literal(annotation: Any) -> bool:
    from typing import Literal

    return get_origin(annotation) is Literal


def _type_name(tp: Any) -> str:
    try:
        return tp.__name__
    except AttributeError:
        return str(tp)


class BaseSettings:
    """Hardened base settings object.

    Subclasses declare settings as annotated class attributes with defaults.

    Example::

        class MySettings(BaseSettings):
            settings_key = "MYAPP"
            FOO: str = "bar"
    """

    # Where to read namespaced dict settings from, e.g. settings.AUDITING
    settings_key: ClassVar[str] = ""
    # Keys that should be import-string resolved
    import_strings: ClassVar[set[str]] = set()
    # Strict mode: error on unknown keys in the namespaced dict
    strict_namespace: ClassVar[bool] = True

    _defaults: ClassVar[dict[str, Any]]
    _types: ClassVar[dict[str, Any]]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        annotations = dict(getattr(cls, "__annotations__", {}))
        public_setting_keys = [k for k in annotations if k.isupper()]

        defaults: dict[str, Any] = {}
        types: dict[str, Any] = {}

        for key in public_setting_keys:
            if key not in cls.__dict__:
                raise ImproperlyConfigured(f"{cls.__name__}.{key} must define a default value")
            defaults[key] = cls.__dict__[key]
            types[key] = annotations[key]

        cls._defaults = defaults
        cls._types = types

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self.reload()

    @property
    def defaults(self) -> dict[str, Any]:
        """Expose for signal handlers and diagnostics."""
        return self._defaults

    @property
    def namespace_setting(self) -> str:
        """Backwards-compatible alias for older code."""
        return self.settings_key

    def is_related_setting(self, setting: str) -> bool:
        return setting == self.settings_key

    def reload(self) -> None:
        """Reload settings from Django settings.

        Reads from ``settings.<settings_key>`` dict, merges with defaults.
        """
        values: dict[str, Any] = deepcopy(self._defaults)

        if self.settings_key:
            namespace_raw = getattr(django_settings, self.settings_key, {})
            if namespace_raw is None:
                namespace_raw = {}
            if not isinstance(namespace_raw, dict):
                raise ImproperlyConfigured(f"{self.settings_key} must be a dictionary.")

            namespace = cast("dict[str, Any]", namespace_raw)
            if self.strict_namespace:
                unknown = set(namespace) - set(self._defaults)
                if unknown:
                    unknown_str = ", ".join(sorted(unknown))
                    raise ImproperlyConfigured(f"Unknown keys in {self.settings_key}: {unknown_str}")

            for key, val in namespace.items():
                if key in self._defaults:
                    values[key] = val

        self._validate(values)

        # Freeze in one place, then expose as real attributes for performance.
        object.__setattr__(self, "_values", values)
        for key, val in values.items():
            object.__setattr__(self, key, val)

    def _validate(self, values: dict[str, Any]) -> None:
        errors: list[str] = []
        for key, expected_type in self._types.items():
            val = values.get(key)
            if not self._is_compatible(val, expected_type):
                errors.append(
                    f"{key}: Invalid type. Expected {_type_name(expected_type)}, got {_type_name(type(val))}."
                )

        if errors:
            raise ImproperlyConfigured("\n".join(errors))

    def _is_compatible(self, value: Any, expected_type: Any) -> bool:
        if expected_type is Any:
            return True

        origin = get_origin(expected_type)

        # Literal[...]
        if _is_literal(expected_type):
            allowed = get_args(expected_type)
            return value in allowed

        # Union / Optional / PEP604 (T | None) -- handles both typing.Union and types.UnionType
        if origin is UnionType or origin is Union:
            return any(self._is_compatible(value, arg) for arg in get_args(expected_type))

        # Parameterized containers: list[str], dict[str, int], etc.
        if origin is not None:
            if not isinstance(value, origin):
                return False
            args = get_args(expected_type)
            if not args:
                return True

            # Shallow element checks for common containers.
            if origin is list and len(args) == 1:
                return all(self._is_compatible(v, args[0]) for v in value)
            if origin is set and len(args) == 1:
                return all(self._is_compatible(v, args[0]) for v in value)
            if origin is dict and len(args) == 2:
                kt, vt = args
                return all(self._is_compatible(k, kt) and self._is_compatible(v, vt) for k, v in value.items())
            return True

        # Normal types
        try:
            return isinstance(value, expected_type)
        except TypeError:
            # Some typing constructs can't be used with isinstance.
            return True

    @overload
    def get(self, key: str) -> Any: ...

    @overload
    def get(self, key: str, default: T) -> T: ...

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def __setattr__(self, name: str, value: Any) -> None:
        # Prevent runtime mutation of declared settings keys.
        if name.isupper() and name in self._defaults:
            raise AttributeError("Settings are read-only; update Django settings and call reload().")
        super().__setattr__(name, value)


__all__ = [
    "BaseSettings",
]
