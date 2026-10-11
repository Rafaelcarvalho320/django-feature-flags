"""The function application code calls.

Deliberately one obvious entry point. A flag API with six ways to ask the same
question is one where two of them disagree.
"""

from __future__ import annotations

from typing import Any

from feature_flags.cache import get_flag
from feature_flags.evaluate import evaluate

#: Attribute used to memoise answers for the duration of one request. A
#: template that checks the same flag in three places should not evaluate the
#: allowlist queries three times.
_REQUEST_CACHE = "_feature_flags_cache"


def flag_is_active(request: Any, name: str) -> bool:
    """Whether ``name`` is on for this request.

    Accepts ``None`` for the request, which is what a management command or a
    Celery task has. The flag is then evaluated with no user, so only a
    fully-on flag comes back true.
    """
    if request is None:
        return evaluate(get_flag(name), None)

    memo = getattr(request, _REQUEST_CACHE, None)
    if memo is None:
        memo = {}
        setattr(request, _REQUEST_CACHE, memo)
    if name in memo:
        return bool(memo[name])

    result = evaluate(get_flag(name), getattr(request, "user", None))
    memo[name] = result
    return result


def flag_is_active_for_user(user: Any, name: str) -> bool:
    """The same decision for a user with no request in hand.

    For a nightly job that has to agree with what the user sees in the browser.
    """
    return evaluate(get_flag(name), user)
