"""Django typing utilities.

Goal
----
Provide reusable typing primitives for Django patterns used throughout the repo.

Why TypeVars instead of subclassing mixins
-----------------------------------------
We avoid making mixins inherit from `models.QuerySet`/`models.Manager` at runtime to
prevent diamond inheritance / MRO surprises. Instead, we annotate `self` with these
TypeVars (bound to Django base classes) so Pylance/Pyright can provide autocomplete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from django.db import models

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


if TYPE_CHECKING:

    class QuerySetMixinBase(models.QuerySet):
        """Typing-only base for QuerySet mixins.

        At runtime this is replaced with a plain object base to avoid changing MRO.
        """

    class ManagerMixinBase(models.Manager):
        """Typing-only base for Manager mixins.

        At runtime this is replaced with a plain object base to avoid changing MRO.
        """

else:

    class QuerySetMixinBase:  # noqa: D101
        pass

    class ManagerMixinBase:  # noqa: D101
        pass


DjangoDeleteReturn = tuple[int, dict[str, int]]

QuerySetT = TypeVar("QuerySetT", bound=models.QuerySet)
ManagerT = TypeVar("ManagerT", bound=models.Manager)


QuerySetProtoT = TypeVar("QuerySetProtoT", bound="QuerySetProtocol")

SoftDeleteQuerySetProtoT = TypeVar("SoftDeleteQuerySetProtoT", bound="SoftDeleteQuerySetProtocol")


class QuerySetProtocol(Protocol):
    """Structural protocol for a Django QuerySet with fluent chaining.

    This is intentionally minimal and focuses on the methods we use in core mixins.
    It improves Pylance/Pyright autocomplete when mixing behaviors into QuerySet
    subclasses.
    """

    model: type[models.Model]

    def filter(self: QuerySetProtoT, *args: Any, **kwargs: Any) -> QuerySetProtoT: ...

    def none(self: QuerySetProtoT) -> QuerySetProtoT: ...

    def using(self: QuerySetProtoT, alias: str) -> QuerySetProtoT: ...

    def update(self, **kwargs: Any) -> int: ...

    def bulk_update(
        self,
        objs: Iterable[models.Model],
        fields: Sequence[str],
        batch_size: int | None = None,
    ) -> int: ...

    def delete(self, using: str | None = None, keep_parents: bool = False) -> DjangoDeleteReturn: ...


class SoftDeleteQuerySetProtocol(QuerySetProtocol, Protocol):
    """QuerySet protocol that includes the repo's soft-delete helpers.

    Use this for typing `self` in mixins that implement `.soft_delete()`/`.restore()`.
    This is what makes `self.soft_delete(...)` show up in Pylance autocomplete inside
    the mixin itself.
    """

    def active(self: SoftDeleteQuerySetProtoT) -> SoftDeleteQuerySetProtoT: ...

    def deleted(self: SoftDeleteQuerySetProtoT) -> SoftDeleteQuerySetProtoT: ...

    def soft_delete(
        self: SoftDeleteQuerySetProtoT,
        using: str | None = None,
        keep_parents: bool = False,
    ) -> DjangoDeleteReturn: ...

    def restore(self) -> int: ...

    def hard_delete(self, using: str | None = None, keep_parents: bool = False) -> DjangoDeleteReturn: ...


class ManagerProtocol(Protocol):
    """Structural protocol for a Django Manager.

    This mainly exists to help Pylance treat `get_queryset()` as returning a queryset
    that supports our fluent methods.
    """

    def get_queryset(self) -> QuerySetProtocol: ...


__all__ = [
    "DjangoDeleteReturn",
    "ManagerMixinBase",
    "ManagerProtocol",
    "ManagerT",
    "QuerySetMixinBase",
    "QuerySetProtocol",
    "QuerySetProtoT",
    "SoftDeleteQuerySetProtocol",
    "SoftDeleteQuerySetProtoT",
    "QuerySetT",
]
