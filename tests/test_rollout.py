"""The bucketing, which is where a rollout is either sticky or useless."""

from __future__ import annotations

import pytest

from feature_flags.rollout import BUCKETS, bucket_of, in_rollout


class TestStability:
    def test_the_same_subject_always_lands_in_the_same_bucket(self) -> None:
        first = bucket_of("new-checkout", "42")
        for _ in range(100):
            assert bucket_of("new-checkout", "42") == first

    def test_the_bucket_does_not_depend_on_the_process(self) -> None:
        """Python's hash() is salted per process, so it would differ in every
        worker and a user would flicker between workers. This is the digest
        pinned against a known value to keep that from creeping back in."""
        assert bucket_of("new-checkout", "42") == bucket_of("new-checkout", "42")
        # A literal, so a change of hash function is a deliberate decision and
        # not an accident that silently reshuffles every live rollout.
        assert bucket_of("flag", "1") == 56

    def test_buckets_are_in_range(self) -> None:
        for subject in range(500):
            assert 0 <= bucket_of("f", str(subject)) < BUCKETS


class TestIndependence:
    def test_two_flags_bucket_the_same_user_differently(self) -> None:
        """Otherwise the unlucky user is first into every single rollout."""
        a = [bucket_of("flag-a", str(n)) for n in range(200)]
        b = [bucket_of("flag-b", str(n)) for n in range(200)]
        assert a != b

    def test_two_subjects_usually_differ(self) -> None:
        assert bucket_of("f", "1") != bucket_of("f", "2")


class TestDistribution:
    def test_a_percentage_selects_roughly_that_share(self) -> None:
        subjects = [str(n) for n in range(10_000)]
        included = sum(1 for s in subjects if in_rollout("f", s, 10))
        # Within two points of 10% over ten thousand subjects. A cheap mixing
        # function does not reliably give this, which is why the digest is
        # cryptographic and not something faster.
        assert 800 <= included <= 1200

    def test_fifty_percent_is_about_half(self) -> None:
        subjects = [str(n) for n in range(10_000)]
        included = sum(1 for s in subjects if in_rollout("f", s, 50))
        assert 4700 <= included <= 5300


class TestMonotonicity:
    def test_raising_the_percentage_only_ever_adds_subjects(self) -> None:
        """What makes a gradual rollout safe to turn up.

        A random draw per request could never promise this: raising 10% to 20%
        would reshuffle everybody instead of adding half as many again.
        """
        subjects = [str(n) for n in range(1_000)]
        previous: set[str] = set()
        for percentage in range(0, 101, 5):
            current = {s for s in subjects if in_rollout("f", s, percentage)}
            assert previous <= current, f"shrank at {percentage}%"
            previous = current

    @pytest.mark.parametrize("percentage", [0, -1, -100])
    def test_zero_or_less_includes_nobody(self, percentage: int) -> None:
        assert not any(in_rollout("f", str(n), percentage) for n in range(200))

    @pytest.mark.parametrize("percentage", [100, 101, 1000])
    def test_a_hundred_or_more_includes_everybody(self, percentage: int) -> None:
        assert all(in_rollout("f", str(n), percentage) for n in range(200))
