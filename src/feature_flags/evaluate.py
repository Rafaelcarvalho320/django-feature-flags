"""The decision: is this flag on, for this request?

The order of the rules is the whole contract, so it is written once here and
nowhere else:

1. **The flag does not exist** -> off. A missing flag is off rather than on,
   because the alternative is that deleting a row, or a typo in a flag name,
   silently ships a half-built feature to everybody.
2. **``enabled`` is off** -> off. The master switch is the thing somebody
   reaches for during an incident, so nothing below can override it.
3. **Outside the time window** -> off.
4. **``staff_only`` and the user is not staff** -> off. A gate, not a rule:
   being on an allowlist does not get a non-staff user past it.
5. **The user is on the allowlist, or in an allowed group** -> on. Above the
   percentage, so the team can see a feature regardless of its bucket.
6. **Inside the percentage rollout** -> on, stickily.
7. Otherwise -> off.

An anonymous request has no identity to bucket, so it can only be reached by
rules 5 and 6 when the percentage is 100. Bucketing by session key was the
alternative and was rejected: a session that rotates moves the user between
buckets, which is exactly the flicker the rollout design exists to avoid.
"""

from __future__ import annotations

from typing import Any

from feature_flags.models import Flag
from feature_flags.rollout import in_rollout


def subject_of(user: Any) -> str | None:
    """The stable identity to bucket a user by, or ``None`` if there is none.

    The primary key, not the username: a rename must not move somebody between
    buckets halfway through a rollout.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    pk = getattr(user, "pk", None)
    return None if pk is None else str(pk)


def user_is_listed(flag: Flag, user: Any) -> bool:
    """Whether the user is named directly or through a group.

    Two queries at most, and only reached for a flag that has an allowlist at
    all, which the caller checks first.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if flag.users.filter(pk=user.pk).exists():
        return True
    return flag.groups.filter(user__pk=user.pk).exists()


def has_allowlist(flag: Flag) -> bool:
    return flag.users.exists() or flag.groups.exists()


def evaluate(flag: Flag | None, user: Any = None) -> bool:
    """Apply the rules above. See the module docstring for the order."""
    if flag is None:
        return False
    if not flag.enabled:
        return False
    if not flag.within_window:
        return False
    if flag.staff_only and not getattr(user, "is_staff", False):
        return False

    if has_allowlist(flag) and user_is_listed(flag, user):
        return True

    if flag.percentage >= 100:
        return True

    subject = subject_of(user)
    if subject is None:
        # Nothing stable to bucket by. Off rather than a coin flip, which would
        # give one visitor different answers on consecutive page loads.
        return False

    return in_rollout(flag.name, subject, flag.percentage)
