"""Deciding whether one subject falls inside a percentage rollout.

The requirement that shapes everything here: the answer must be **sticky**. A
user who sees a feature at 10:00 has to still see it at 10:01, and at 10% has
to be in the same bucket as at 11%, or a rollout turns into a flicker that
makes the feature look broken and the metrics meaningless.

Storing an assignment per user per flag would do it, at the cost of a table
that grows with users times flags and has to be written on first sight. The
cheaper answer is to derive the bucket, so it is reproducible from the two
things already in hand: who the subject is and which flag is being asked
about.

Two properties the derivation needs:

* **Stable across processes and restarts.** Python's ``hash()`` is salted per
  process for strings, so it gives a different answer in every worker. That is
  the one function that must not be used here, and it is the obvious one to
  reach for.
* **Independent per flag.** The flag name goes into the digest, so a user
  unlucky in one rollout is not systematically first in every other one.
"""

from __future__ import annotations

import hashlib

#: Buckets. A hundred, so the percentage is the bucket count and the arithmetic
#: needs no explanation.
BUCKETS = 100


def bucket_of(flag_name: str, subject: str) -> int:
    """A stable bucket in ``range(BUCKETS)`` for this subject and this flag.

    Uses a cryptographic digest, not for secrecy but for distribution: the
    output is uniform enough that a 10% rollout really is about a tenth of
    subjects, which a cheaper mixing function does not reliably give.
    """
    digest = hashlib.sha256(f"{flag_name}:{subject}".encode()).digest()
    # Four bytes is plenty of range for a hundred buckets and keeps the
    # arithmetic in machine-int territory.
    return int.from_bytes(digest[:4], "big") % BUCKETS


def in_rollout(flag_name: str, subject: str, percentage: int) -> bool:
    """Whether ``subject`` is inside a ``percentage`` rollout of ``flag_name``.

    Monotonic in ``percentage`` by construction: raising it can only add
    subjects, never move one out. That is what makes a gradual rollout safe to
    turn up, and what a random draw per request could never promise.
    """
    if percentage <= 0:
        return False
    if percentage >= BUCKETS:
        return True
    return bucket_of(flag_name, subject) < percentage
