"""Template access to flags.

    {% load feature_flags %}

    {% if "new-checkout"|flag_active:request %}...{% endif %}

    {% flag "new-checkout" as new_checkout %}
    {% if new_checkout %}...{% endif %}

Two spellings because both read better in different places: the filter inside
an existing condition, the tag when the answer is used more than once.
"""

from __future__ import annotations

from typing import Any

from django import template

from feature_flags.api import flag_is_active

register = template.Library()


@register.simple_tag(takes_context=True)
def flag(context: template.Context, name: str) -> bool:
    """Reads the request from the context, so the user is taken into account.

    Returns False when there is no request rather than raising: a template
    rendered without a request context (an email, say) should fall back to the
    old behaviour, not break.
    """
    return flag_is_active(context.get("request"), name)


@register.filter(name="flag_active")
def flag_active(name: str, request: Any = None) -> bool:
    return flag_is_active(request, name)
