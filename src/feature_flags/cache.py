"""Caching the flag rows.

A flag is read on most requests, often several times in one template, and the
row almost never changes. Reading the table every time is a query bought for
nothing, so the rows are cached and the cache is cleared whenever a flag is
saved or deleted.

The whole set is cached under one key rather than one key per flag. A page that
checks six flags then costs one cache read instead of six, and clearing is a
single delete with no chance of a half-stale set.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from feature_flags.models import Flag

CACHE_KEY = "feature_flags:all"

#: Five minutes. Short enough that a cache cleared on a different web server
#: is not the only thing standing between a toggle and taking effect, long
#: enough to be worth having. Invalidation on save is the fast path; this is
#: the safety net for a multi-process deployment with a local-memory cache,
#: where one worker's signal never reaches another's cache.
CACHE_TIMEOUT = 300


def all_flags(*, use_cache: bool = True) -> dict[str, Flag]:
    """Every flag, keyed by name."""
    if use_cache:
        cached = cache.get(CACHE_KEY)
        if isinstance(cached, dict):
            return cached

    flags = {flag.name: flag for flag in Flag.objects.all()}
    if use_cache:
        cache.set(CACHE_KEY, flags, CACHE_TIMEOUT)
    return flags


def get_flag(name: str, *, use_cache: bool = True) -> Flag | None:
    return all_flags(use_cache=use_cache).get(name)


def clear() -> None:
    cache.delete(CACHE_KEY)


@receiver(post_save, sender=Flag)
@receiver(post_delete, sender=Flag)
def _clear_on_change(sender: type[Flag], **kwargs: Any) -> None:
    clear()


@receiver(m2m_changed, sender=Flag.users.through)
@receiver(m2m_changed, sender=Flag.groups.through)
def _clear_on_allowlist_change(sender: Any, **kwargs: Any) -> None:
    """The allowlists are separate tables, so saving the flag is not involved.

    Without this, adding somebody to a flag's user list changes nothing until
    the timeout expires, which reads as the feature being broken.
    """
    clear()
