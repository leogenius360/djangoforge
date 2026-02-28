"""
Lightweight serializer framework for the DjangoForge API layer.

Provides ``Serializer`` and ``ModelSerializer`` classes that handle
request validation and response serialization without requiring DRF.
The API is intentionally compatible with DRF serializer conventions
(``is_valid()``, ``validated_data``, ``errors``, ``data``) so that
migration from DRF is straightforward.
"""

from __future__ import annotations

import copy
import re
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.dateparse import parse_date, parse_datetime, parse_time

from apps.core.api.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Field classes
# ---------------------------------------------------------------------------


class _Empty:
    """Sentinel for missing values."""


empty = _Empty()


class Field:
    """Base field class."""

    default_error_messages = {
        "required": "This field is required.",
        "null": "This field may not be null.",
        "invalid": "Invalid value.",
    }

    def __init__(
        self,
        *,
        read_only: bool = False,
        write_only: bool = False,
        required: bool | None = None,
        default: Any = empty,
        allow_null: bool = False,
        allow_blank: bool = False,
        source: str | None = None,
        label: str | None = None,
        help_text: str | None = None,
        error_messages: dict | None = None,
        validators: list | None = None,
    ):
        self.read_only = read_only
        self.write_only = write_only
        self._required = required
        self.default = default
        self.allow_null = allow_null
        self.allow_blank = allow_blank
        self.source = source
        self.label = label
        self.help_text = help_text
        self.validators = validators or []
        self.field_name: str = ""
        self.parent: Serializer | None = None

        if error_messages:
            self.error_messages = {**self.default_error_messages, **error_messages}
        else:
            self.error_messages = dict(self.default_error_messages)

    @property
    def required(self) -> bool:
        if self._required is not None:
            return self._required
        return not self.read_only and isinstance(self.default, _Empty)

    def bind(self, field_name: str, parent: Serializer) -> None:
        self.field_name = field_name
        self.parent = parent
        if self.source is None:
            self.source = field_name

    def get_default(self) -> Any:
        if isinstance(self.default, _Empty):
            raise ValidationError(self.error_messages["required"])
        if callable(self.default):
            return self.default()
        return self.default

    def run_validation(self, data: Any) -> Any:
        if isinstance(data, _Empty):
            if self.required:
                raise ValidationError(self.error_messages["required"])
            return self.get_default()
        if data is None:
            if not self.allow_null:
                raise ValidationError(self.error_messages["null"])
            return None
        value = self.to_internal_value(data)
        for validator in self.validators:
            validator(value)
        return value

    def to_internal_value(self, data: Any) -> Any:
        return data

    def to_representation(self, value: Any) -> Any:
        return value


class CharField(Field):
    default_error_messages = {
        **Field.default_error_messages,
        "blank": "This field may not be blank.",
        "max_length": "Ensure this field has no more than {max_length} characters.",
        "min_length": "Ensure this field has at least {min_length} characters.",
    }

    def __init__(self, *, max_length: int | None = None, min_length: int | None = None, trim_whitespace: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length
        self.min_length = min_length
        self.trim_whitespace = trim_whitespace

    def to_internal_value(self, data: Any) -> str:
        value = str(data)
        if self.trim_whitespace:
            value = value.strip()
        if not self.allow_blank and value == "":
            raise ValidationError(self.error_messages["blank"])
        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError(self.error_messages["max_length"].format(max_length=self.max_length))
        if self.min_length is not None and len(value) < self.min_length:
            raise ValidationError(self.error_messages["min_length"].format(min_length=self.min_length))
        return value


class EmailField(CharField):
    default_error_messages = {**CharField.default_error_messages, "invalid": "Enter a valid email address."}

    _email_re = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data)
        if not self._email_re.match(value):
            raise ValidationError(self.error_messages["invalid"])
        return value.lower()


class IntegerField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid": "A valid integer is required."}

    def __init__(self, *, min_value: int | None = None, max_value: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value

    def to_internal_value(self, data: Any) -> int:
        try:
            value = int(data)
        except (TypeError, ValueError) as e:
            raise ValidationError(self.error_messages["invalid"]) from e
        if self.min_value is not None and value < self.min_value:
            raise ValidationError(f"Ensure this value is greater than or equal to {self.min_value}.")
        if self.max_value is not None and value > self.max_value:
            raise ValidationError(f"Ensure this value is less than or equal to {self.max_value}.")
        return value


class FloatField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid": "A valid number is required."}

    def to_internal_value(self, data: Any) -> float:
        try:
            return float(data)
        except (TypeError, ValueError) as e:
            raise ValidationError(self.error_messages["invalid"]) from e


class DecimalField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid": "A valid number is required."}

    def __init__(self, *, max_digits: int | None = None, decimal_places: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.max_digits = max_digits
        self.decimal_places = decimal_places

    def to_internal_value(self, data: Any) -> Decimal:
        try:
            return Decimal(str(data))
        except (InvalidOperation, TypeError, ValueError) as e:
            raise ValidationError(self.error_messages["invalid"]) from e


class BooleanField(Field):
    TRUE_VALUES = {True, "true", "True", "TRUE", "1", 1, "yes", "Yes", "YES", "on"}
    FALSE_VALUES = {False, "false", "False", "FALSE", "0", 0, "no", "No", "NO", "off"}

    def to_internal_value(self, data: Any) -> bool:
        if data in self.TRUE_VALUES:
            return True
        if data in self.FALSE_VALUES:
            return False
        raise ValidationError(self.error_messages["invalid"])

    def to_representation(self, value: Any) -> bool:
        return bool(value)


class DateTimeField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid": "Datetime has wrong format."}

    def to_internal_value(self, data: Any) -> datetime:
        if isinstance(data, datetime):
            return data
        if isinstance(data, str):
            parsed = parse_datetime(data)
            if parsed is not None:
                return parsed
        raise ValidationError(self.error_messages["invalid"])

    def to_representation(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)


class DateField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid": "Date has wrong format."}

    def to_internal_value(self, data: Any) -> date:
        if isinstance(data, date) and not isinstance(data, datetime):
            return data
        if isinstance(data, str):
            parsed = parse_date(data)
            if parsed is not None:
                return parsed
        raise ValidationError(self.error_messages["invalid"])

    def to_representation(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        return str(value)


class TimeField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid": "Time has wrong format."}

    def to_internal_value(self, data: Any) -> time:
        if isinstance(data, time):
            return data
        if isinstance(data, str):
            parsed = parse_time(data)
            if parsed is not None:
                return parsed
        raise ValidationError(self.error_messages["invalid"])

    def to_representation(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, time):
            return value.isoformat()
        return str(value)


class DurationField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid": "Duration has wrong format."}

    def to_internal_value(self, data: Any) -> timedelta:
        if isinstance(data, timedelta):
            return data
        if isinstance(data, (int, float)):
            return timedelta(seconds=data)
        raise ValidationError(self.error_messages["invalid"])

    def to_representation(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, timedelta):
            return value.total_seconds()
        return value


class UUIDField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid": "Must be a valid UUID."}

    def to_internal_value(self, data: Any) -> uuid.UUID:
        if isinstance(data, uuid.UUID):
            return data
        try:
            return uuid.UUID(str(data))
        except (ValueError, AttributeError) as e:
            raise ValidationError(self.error_messages["invalid"]) from e

    def to_representation(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


class ChoiceField(Field):
    default_error_messages = {**Field.default_error_messages, "invalid_choice": '"{input}" is not a valid choice.'}

    def __init__(self, choices: list | tuple, **kwargs):
        super().__init__(**kwargs)
        self.choices = choices
        # Normalize to list of values
        self._valid_values = set()
        for choice in choices:
            if isinstance(choice, (list, tuple)):
                self._valid_values.add(choice[0])
            else:
                self._valid_values.add(choice)

    def to_internal_value(self, data: Any) -> Any:
        if data not in self._valid_values:
            raise ValidationError(self.error_messages["invalid_choice"].format(input=data))
        return data


class ListField(Field):
    default_error_messages = {**Field.default_error_messages, "not_a_list": 'Expected a list of items but got type "{input_type}".'}

    def __init__(self, child: Field | None = None, **kwargs):
        super().__init__(**kwargs)
        self.child = child

    def to_internal_value(self, data: Any) -> list:
        if not isinstance(data, list):
            raise ValidationError(self.error_messages["not_a_list"].format(input_type=type(data).__name__))
        if self.child is None:
            return data
        result = []
        errors = []
        for item in data:
            try:
                result.append(self.child.run_validation(item))
            except ValidationError as e:
                errors.append(e.detail)
        if errors:
            raise ValidationError(errors)
        return result


class DictField(Field):
    default_error_messages = {**Field.default_error_messages, "not_a_dict": 'Expected a dictionary but got type "{input_type}".'}

    def to_internal_value(self, data: Any) -> dict:
        if not isinstance(data, dict):
            raise ValidationError(self.error_messages["not_a_dict"].format(input_type=type(data).__name__))
        return data


class JSONField(Field):
    """Accepts any JSON-serializable value (dict, list, string, number, bool, null)."""

    def to_internal_value(self, data: Any) -> Any:
        return data


class SlugRelatedField(Field):
    """Look up related objects by a slug field."""

    default_error_messages = {
        **Field.default_error_messages,
        "does_not_exist": 'Object with {slug_name}="{value}" does not exist.',
    }

    def __init__(self, *, slug_field: str, queryset: Any = None, **kwargs):
        super().__init__(**kwargs)
        self.slug_field = slug_field
        self.queryset = queryset

    def to_internal_value(self, data: Any) -> Any:
        if self.queryset is None:
            raise ValidationError("queryset is required for writable SlugRelatedField")
        try:
            return self.queryset.get(**{self.slug_field: data})
        except ObjectDoesNotExist as e:
            raise ValidationError(
                self.error_messages["does_not_exist"].format(slug_name=self.slug_field, value=data)
            ) from e


class PrimaryKeyRelatedField(Field):
    """Look up related objects by primary key."""

    default_error_messages = {
        **Field.default_error_messages,
        "does_not_exist": 'Invalid pk "{pk_value}" - object does not exist.',
        "incorrect_type": "Incorrect type. Expected pk value, received {data_type}.",
    }

    def __init__(self, *, queryset: Any = None, many: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.queryset = queryset
        self.many = many

    def to_internal_value(self, data: Any) -> Any:
        if self.queryset is None:
            raise ValidationError("queryset is required for writable PrimaryKeyRelatedField")
        if self.many:
            if not isinstance(data, list):
                raise ValidationError("Expected a list of primary keys.")
            result = []
            for pk in data:
                try:
                    result.append(self.queryset.get(pk=pk))
                except (ObjectDoesNotExist, TypeError, ValueError) as e:
                    raise ValidationError(self.error_messages["does_not_exist"].format(pk_value=pk)) from e
            return result
        try:
            return self.queryset.get(pk=data)
        except (ObjectDoesNotExist, TypeError, ValueError) as e:
            raise ValidationError(self.error_messages["does_not_exist"].format(pk_value=data)) from e

    def to_representation(self, value: Any) -> Any:
        if hasattr(value, "pk"):
            pk = value.pk
            return str(pk) if isinstance(pk, uuid.UUID) else pk
        return value


class SerializerMethodField(Field):
    """Read-only field that calls a method on the parent serializer."""

    def __init__(self, method_name: str | None = None, **kwargs):
        kwargs["read_only"] = True
        kwargs["source"] = "*"
        super().__init__(**kwargs)
        self.method_name = method_name

    def bind(self, field_name: str, parent: Serializer) -> None:
        if self.method_name is None:
            self.method_name = f"get_{field_name}"
        super().bind(field_name, parent)

    def to_representation(self, value: Any) -> Any:
        method = getattr(self.parent, self.method_name)
        return method(value)


class HiddenField(Field):
    """A field that does not take input from the user."""

    def __init__(self, **kwargs):
        kwargs["write_only"] = True
        super().__init__(**kwargs)


# ---------------------------------------------------------------------------
# Serializer metaclass
# ---------------------------------------------------------------------------


class SerializerMetaclass(type):
    """Collect declared ``Field`` instances into ``_declared_fields``."""

    def __new__(mcs, name, bases, namespace):
        fields = {}
        # Inherit from parents
        for base in reversed(bases):
            if hasattr(base, "_declared_fields"):
                fields.update(base._declared_fields)
        # Collect from current class
        for key, value in list(namespace.items()):
            if isinstance(value, Field):
                fields[key] = value
        namespace["_declared_fields"] = fields
        return super().__new__(mcs, name, bases, namespace)


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


class Serializer(metaclass=SerializerMetaclass):
    """
    Pure Django serializer for request validation and response serialization.

    Usage mirrors DRF:
        serializer = MySerializer(data=request_data)
        serializer.is_valid(raise_exception=True)
        cleaned = serializer.validated_data
    """

    _declared_fields: dict[str, Field]

    def __init__(
        self,
        instance: Any = None,
        data: Any = empty,
        *,
        many: bool = False,
        context: dict | None = None,
        partial: bool = False,
        **kwargs,
    ):
        self.instance = instance
        self.initial_data = data
        self.many = many
        self.partial = partial
        self.context = context or {}
        self._validated_data: Any = empty
        self._errors: dict | list = {}

        # Bind fields
        self.fields: dict[str, Field] = {}
        for name, field in self._declared_fields.items():
            field_copy = copy.deepcopy(field)
            field_copy.bind(name, self)
            self.fields[name] = field_copy

    # ── Validation ──────────────────────────────────────────────────

    def is_valid(self, *, raise_exception: bool = False) -> bool:
        if not isinstance(self.initial_data, _Empty):
            try:
                if self.many:
                    self._validated_data = self._validate_many(self.initial_data)
                else:
                    self._validated_data = self._validate(self.initial_data)
            except ValidationError as exc:
                self._errors = exc.detail if isinstance(exc.detail, (dict, list)) else {"non_field_errors": [str(exc.detail)]}
        else:
            self._errors = {"non_field_errors": ["No data provided."]}

        if self._errors and raise_exception:
            raise ValidationError(self._errors)
        return not bool(self._errors)

    def _validate(self, data: dict) -> dict:
        if not isinstance(data, dict):
            raise ValidationError("Expected a dictionary.")

        errors: dict[str, list] = {}
        result: dict[str, Any] = {}

        for field_name, field in self.fields.items():
            if field.read_only:
                continue
            value = data.get(field_name, empty)
            if isinstance(value, _Empty) and self.partial and not field.required:
                continue
            try:
                validated = field.run_validation(value)
                result[field.source or field_name] = validated
            except ValidationError as exc:
                detail = exc.detail
                errors[field_name] = detail if isinstance(detail, list) else [str(detail)]

        if errors:
            raise ValidationError(errors)

        # Run custom field validators
        for field_name in list(result.keys()):
            method = getattr(self, f"validate_{field_name}", None)
            if method:
                try:
                    result[field_name] = method(result[field_name])
                except ValidationError as exc:
                    errors[field_name] = [str(exc.detail)] if isinstance(exc.detail, str) else exc.detail

        if errors:
            raise ValidationError(errors)

        # Run object-level validation
        try:
            result = self.validate(result)
        except ValidationError as exc:
            if isinstance(exc.detail, dict):
                raise
            raise ValidationError({"non_field_errors": [str(exc.detail)]}) from exc

        return result

    def _validate_many(self, data: list) -> list:
        if not isinstance(data, list):
            raise ValidationError("Expected a list.")
        results = []
        errors = []
        for item in data:
            try:
                results.append(self._validate(item))
                errors.append({})
            except ValidationError as exc:
                results.append({})
                errors.append(exc.detail)
        if any(errors):
            raise ValidationError(errors)
        return results

    def validate(self, attrs: dict) -> dict:
        """Override for object-level validation."""
        return attrs

    # ── Properties ──────────────────────────────────────────────────

    @property
    def validated_data(self) -> Any:
        if isinstance(self._validated_data, _Empty):
            msg = "You must call `.is_valid()` before accessing `.validated_data`."
            raise AssertionError(msg)
        return self._validated_data

    @property
    def errors(self) -> dict | list:
        return self._errors

    @property
    def data(self) -> Any:
        if self.instance is not None:
            if self.many:
                return [self.to_representation(item) for item in self.instance]
            return self.to_representation(self.instance)
        if not isinstance(self._validated_data, _Empty):
            if self.many:
                return self._validated_data
            return self._validated_data
        return {}

    # ── Representation ──────────────────────────────────────────────

    def to_representation(self, instance: Any) -> dict:
        result = {}
        for field_name, field in self.fields.items():
            if field.write_only:
                continue
            try:
                if isinstance(field, SerializerMethodField):
                    value = field.to_representation(instance)
                else:
                    source = field.source or field_name
                    if source == "*":
                        value = field.to_representation(instance)
                    else:
                        value = self._get_attribute(instance, source)
                        value = field.to_representation(value)
                result[field_name] = value
            except (AttributeError, KeyError, TypeError):
                result[field_name] = None
        return result

    def _get_attribute(self, instance: Any, source: str) -> Any:
        parts = source.split(".")
        obj = instance
        for part in parts:
            if isinstance(obj, dict):
                obj = obj[part]
            else:
                obj = getattr(obj, part)
                if callable(obj):
                    obj = obj()
        return obj

    # ── CRUD hooks ──────────────────────────────────────────────────

    def create(self, validated_data: dict) -> Any:
        raise NotImplementedError

    def update(self, instance: Any, validated_data: dict) -> Any:
        raise NotImplementedError

    def save(self, **kwargs) -> Any:
        validated = {**self.validated_data, **kwargs}
        if self.instance is not None:
            self.instance = self.update(self.instance, validated)
        else:
            self.instance = self.create(validated)
        return self.instance


# ---------------------------------------------------------------------------
# ModelSerializer
# ---------------------------------------------------------------------------

# Field mapping from Django model fields to serializer fields
_MODEL_FIELD_MAPPING: dict[type, type[Field]] = {
    models.CharField: CharField,
    models.TextField: CharField,
    models.EmailField: EmailField,
    models.SlugField: CharField,
    models.URLField: CharField,
    models.IntegerField: IntegerField,
    models.SmallIntegerField: IntegerField,
    models.BigIntegerField: IntegerField,
    models.PositiveIntegerField: IntegerField,
    models.PositiveSmallIntegerField: IntegerField,
    models.PositiveBigIntegerField: IntegerField,
    models.FloatField: FloatField,
    models.DecimalField: DecimalField,
    models.BooleanField: BooleanField,
    models.NullBooleanField: BooleanField,
    models.DateTimeField: DateTimeField,
    models.DateField: DateField,
    models.TimeField: TimeField,
    models.DurationField: DurationField,
    models.UUIDField: UUIDField,
    models.JSONField: JSONField,
    models.AutoField: IntegerField,
    models.BigAutoField: IntegerField,
    models.SmallAutoField: IntegerField,
    models.ForeignKey: PrimaryKeyRelatedField,
    models.OneToOneField: PrimaryKeyRelatedField,
}


class ModelSerializer(Serializer):
    """
    Serializer that auto-generates fields from a Django model.

    Usage::

        class UserSerializer(ModelSerializer):
            class Meta:
                model = User
                fields = ["id", "username", "email"]
                read_only_fields = ["id"]
    """

    class Meta:
        model: type[models.Model] | None = None
        fields: list[str] | str = []
        exclude: list[str] = []
        read_only_fields: list[str] = []
        extra_kwargs: dict[str, dict] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "Meta") and self.Meta.model is not None:
            self._build_fields_from_model()

    def _build_fields_from_model(self) -> None:
        model = self.Meta.model
        meta = model._meta  # noqa: SLF001
        model_fields = {f.name: f for f in meta.get_fields() if hasattr(f, "name")}

        # Determine which fields to include
        if self.Meta.fields == "__all__":
            field_names = [f.name for f in meta.get_fields() if hasattr(f, "name") and not f.many_to_many and not f.one_to_many]
        elif self.Meta.fields:
            field_names = list(self.Meta.fields)
        else:
            field_names = []

        if self.Meta.exclude:
            field_names = [f for f in field_names if f not in self.Meta.exclude]

        read_only_fields = set(getattr(self.Meta, "read_only_fields", []) or [])
        extra_kwargs = getattr(self.Meta, "extra_kwargs", {}) or {}

        for name in field_names:
            # Skip if already declared explicitly
            if name in self._declared_fields:
                continue

            model_field = model_fields.get(name)
            if model_field is None:
                continue

            field_class = None
            field_kwargs: dict[str, Any] = {}

            # Handle ForeignKey
            if isinstance(model_field, (models.ForeignKey, models.OneToOneField)):
                field_class = PrimaryKeyRelatedField
                if name not in read_only_fields:
                    field_kwargs["queryset"] = model_field.related_model.objects.all()
            else:
                for model_type, serializer_type in _MODEL_FIELD_MAPPING.items():
                    if isinstance(model_field, model_type):
                        field_class = serializer_type
                        break

            if field_class is None:
                field_class = Field

            # Apply common kwargs
            if name in read_only_fields or name == "id" or name == "pk":
                field_kwargs["read_only"] = True
            if hasattr(model_field, "has_default") and model_field.has_default():
                field_kwargs["required"] = False
            if hasattr(model_field, "null") and model_field.null:
                field_kwargs["allow_null"] = True
                field_kwargs["required"] = False
            if hasattr(model_field, "blank") and model_field.blank:
                field_kwargs.setdefault("required", False)
                if field_class in (CharField, EmailField):
                    field_kwargs["allow_blank"] = True
            if hasattr(model_field, "max_length") and model_field.max_length and field_class == CharField:
                field_kwargs["max_length"] = model_field.max_length
            if hasattr(model_field, "choices") and model_field.choices:
                field_class = ChoiceField
                field_kwargs["choices"] = model_field.choices

            # Apply extra kwargs from Meta
            if name in extra_kwargs:
                field_kwargs.update(extra_kwargs[name])

            field_instance = field_class(**field_kwargs)
            field_instance.bind(name, self)
            self.fields[name] = field_instance

    def create(self, validated_data: dict) -> Any:
        model = self.Meta.model
        return model.objects.create(**validated_data)

    def update(self, instance: Any, validated_data: dict) -> Any:
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
