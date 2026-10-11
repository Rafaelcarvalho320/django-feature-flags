"""django-feature-flags: database-backed feature flags for Django.

    from feature_flags import flag_is_active

    if flag_is_active(request, "new-checkout"):
        ...

Nothing is imported eagerly. A reusable Django app that touches models at
package-import time raises ``AppRegistryNotReady`` the moment anything imports
it before ``django.setup()`` has run, which ``makemigrations`` does. The
PEP 562 hook below keeps the short import path without that.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"

_EXPORTS: dict[str, str] = {
    "Flag": "feature_flags.models",
    "flag_is_active": "feature_flags.api",
    "flag_is_active_for_user": "feature_flags.api",
    "flag_required": "feature_flags.decorators",
    "evaluate": "feature_flags.evaluate",
    "in_rollout": "feature_flags.rollout",
    "bucket_of": "feature_flags.rollout",
}

__all__ = ["__version__", *sorted(_EXPORTS)]


def __getattr__(name: str) -> Any:
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module_path), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
