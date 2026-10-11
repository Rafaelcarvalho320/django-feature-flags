"""Guarding a view with a flag."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect

from feature_flags.api import flag_is_active

ViewFunc = Callable[..., HttpResponse]


def flag_required(
    name: str, *, redirect_to: str | None = None
) -> Callable[[ViewFunc], ViewFunc]:
    """Refuse the view unless ``name`` is on.

    A 404 by default, not a 403. A 403 says "this exists and you may not have
    it", which tells anybody probing that the feature is there; a feature
    behind a flag should be indistinguishable from one that was never built.
    """

    def decorator(view: ViewFunc) -> ViewFunc:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if flag_is_active(request, name):
                return view(request, *args, **kwargs)
            if redirect_to is not None:
                return redirect(redirect_to)
            raise Http404(f"feature {name!r} is not enabled")

        return wrapper

    return decorator
