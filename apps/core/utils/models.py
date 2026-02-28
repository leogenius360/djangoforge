"""
apps.core.utils.models.fields

Fast, deterministic model "has field?" helpers for Django model classes.

What "field" means here
-----------------------
`model_has_field(MyModel, name)` returns True when `name` is a Django-managed
attribute that is part of the ORM schema or relation graph for `MyModel`:

- Forward fields: concrete fields declared on the model (and inherited fields).
- Forward relation attnames: e.g. `author_id` for a ForeignKey named `author`.
- Reverse relation accessors: e.g. `author.books` (FK reverse manager),
  `author.profile` (OneToOne reverse descriptor), when the reverse accessor exists.

It intentionally does NOT try to answer "does Python attribute access succeed?"
(e.g., it won't treat methods/properties/managers as fields).

Notes
-----
- Reverse accessors can be disabled with related_name='+'; in that case there is
  no attribute to access from the reverse side, and we treat it as absent.
- Deferred fields are still fields in the model definition; they remain present.
- Proxy models share the underlying fields; `_meta.get_fields(include_parents=True)`
  covers that transparently.

Performance
-----------
We cache:
1) The computed set of all Django field/relation attribute names for each model class.
2) The per-(model class, name) membership check.
3) The per-model `has_field(name)` callable.

If you dynamically add/modify fields at runtime (uncommon), call:
    clear_model_field_cache()
"""

from __future__ import annotations

from functools import lru_cache, partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model


@lru_cache(maxsize=1024)
def _model_field_name_set(model_cls: type[Model]) -> frozenset[str]:
    """
    Compute the set of Django-managed attribute names that should be treated as
    fields/relations on `model_cls`.

    Includes:
      - `field.name` for forward fields (including inherited fields)
      - `field.attname` for forward fields that define one (e.g., FK `<name>_id`)
      - reverse accessor names for reverse relations that create accessors

    Uses `_meta.get_fields(include_parents=True, include_hidden=True)` so that
    inherited fields and auto-created relation objects are visible.
    """
    opts = model_cls._meta
    names: set[str] = set()

    for f in opts.get_fields(include_parents=True, include_hidden=True):
        is_reverse_rel = getattr(f, "auto_created", False) and not getattr(f, "concrete", False)

        if is_reverse_rel:
            # Reverse relations (FK/M2M/O2O from other models pointing to this model).
            # These expose an accessor attribute unless disabled via related_name='+'.
            accessor: str | None = None
            try:
                accessor = f.get_accessor_name()  # type: ignore[attr-defined]
            except Exception:
                # Extremely defensive; most relation objects implement get_accessor_name().
                accessor = None

            if accessor and accessor != "+":
                names.add(accessor)
            continue

        # Forward fields defined on this model (or inherited via parents).
        fname = getattr(f, "name", None)
        if fname:
            names.add(fname)

        # Forward relation "attname" (e.g., author_id) is a real model attribute and
        # often appears in update_fields / partial updates.
        attname = getattr(f, "attname", None)
        if attname:
            names.add(attname)

    return frozenset(names)


@lru_cache(maxsize=8192)
def model_has_field(model_cls: type[Model], name: str) -> bool:
    """
    Return True if `name` is a Django-managed field/relation attribute on `model_cls`.

    This is safe for use before doing things like `setattr(instance, name, value)`
    because it only returns True for attributes that Django defines for fields and
    relation accessors (including inherited fields and reverse relation accessors).

    For reverse OneToOne accessors, the attribute may raise RelatedObjectDoesNotExist
    when accessed on a particular instance, but the attribute *exists* on the class;
    we return True in that case.
    """
    return name in _model_field_name_set(model_cls)


@lru_cache(maxsize=1024)
def get_has_field_callable(model_cls: type[Model]) -> Callable[[str], bool]:
    """
    Return a `has_field(name) -> bool` callable for `model_cls`.

    Fast path:
      - If the model defines a classmethod `_has_field(name) -> bool`, return it.

    Fallback:
      - Return a cached callable bound to `model_has_field(model_cls, name)`.

    Contract for `_has_field` (if you implement it):
      - It must implement the same semantics as `model_has_field` above (including
        inherited fields and reverse relation accessors), or be a strict superset.
    """
    hook = getattr(model_cls, "_has_field", None)
    if callable(hook):
        return hook  # expected signature: (name: str) -> bool
    return partial(model_has_field, model_cls)


def clear_model_field_cache() -> None:
    """
    Clear all internal caches used by this module.

    Useful in tests that dynamically modify model definitions (uncommon).
    """
    _model_field_name_set.cache_clear()
    model_has_field.cache_clear()
    get_has_field_callable.cache_clear()


__all__ = [
    "model_has_field",
    "get_has_field_callable",
    "clear_model_field_cache",
]
