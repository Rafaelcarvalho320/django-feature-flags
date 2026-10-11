"""The decision rules, in the order the module documents."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.utils import timezone

from feature_flags.evaluate import evaluate, subject_of
from feature_flags.models import Flag

pytestmark = pytest.mark.django_db


class TestMissingFlag:
    def test_a_flag_that_does_not_exist_is_off(self, user: User) -> None:
        """Off rather than on: the alternative is that a typo in a flag name
        ships a half-built feature to everybody."""
        assert evaluate(None, user) is False


class TestMasterSwitch:
    def test_disabled_beats_everything(self, user: User) -> None:
        flag = Flag.objects.create(name="f", enabled=False, percentage=100)
        flag.users.add(user)
        assert evaluate(flag, user) is False

    def test_enabled_at_a_hundred_percent_is_on(self, user: User) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=100)
        assert evaluate(flag, user) is True

    def test_enabled_at_zero_with_no_allowlist_reaches_nobody(self, user: User) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=0)
        assert evaluate(flag, user) is False


class TestWindow:
    def test_before_the_start_it_is_off(self, user: User) -> None:
        flag = Flag.objects.create(
            name="f",
            enabled=True,
            percentage=100,
            starts_at=timezone.now() + timezone.timedelta(hours=1),
        )
        assert evaluate(flag, user) is False

    def test_after_the_end_it_is_off(self, user: User) -> None:
        flag = Flag.objects.create(
            name="f",
            enabled=True,
            percentage=100,
            ends_at=timezone.now() - timezone.timedelta(hours=1),
        )
        assert evaluate(flag, user) is False

    def test_inside_the_window_it_is_on(self, user: User) -> None:
        now = timezone.now()
        flag = Flag.objects.create(
            name="f",
            enabled=True,
            percentage=100,
            starts_at=now - timezone.timedelta(hours=1),
            ends_at=now + timezone.timedelta(hours=1),
        )
        assert evaluate(flag, user) is True

    def test_no_window_means_always(self, user: User) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=100)
        assert flag.within_window is True


class TestStaffGate:
    def test_a_non_staff_user_is_refused(self, user: User) -> None:
        flag = Flag.objects.create(
            name="f", enabled=True, percentage=100, staff_only=True
        )
        assert evaluate(flag, user) is False

    def test_a_staff_user_gets_through(self, staff_user: User) -> None:
        flag = Flag.objects.create(
            name="f", enabled=True, percentage=100, staff_only=True
        )
        assert evaluate(flag, staff_user) is True

    def test_it_is_a_gate_not_a_rule(self, user: User) -> None:
        """Being allowlisted does not get a non-staff user past staff_only."""
        flag = Flag.objects.create(
            name="f", enabled=True, percentage=0, staff_only=True
        )
        flag.users.add(user)
        assert evaluate(flag, user) is False


class TestAllowlists:
    def test_a_listed_user_sees_it_whatever_their_bucket(self, user: User) -> None:
        """Above the percentage on purpose, so the team can see a feature
        regardless of where their bucket happened to fall."""
        flag = Flag.objects.create(name="f", enabled=True, percentage=0)
        flag.users.add(user)
        assert evaluate(flag, user) is True

    def test_an_unlisted_user_does_not(self, user: User, other_user: User) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=0)
        flag.users.add(user)
        assert evaluate(flag, other_user) is False

    def test_a_group_member_sees_it(self, user: User, beta_group: Group) -> None:
        user.groups.add(beta_group)
        flag = Flag.objects.create(name="f", enabled=True, percentage=0)
        flag.groups.add(beta_group)
        assert evaluate(flag, user) is True

    def test_a_non_member_does_not(self, other_user: User, beta_group: Group) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=0)
        flag.groups.add(beta_group)
        assert evaluate(flag, other_user) is False


class TestAnonymous:
    def test_an_anonymous_visitor_is_off_below_a_hundred_percent(self) -> None:
        """Nothing stable to bucket by, and a coin flip would give one visitor
        different answers on consecutive page loads."""
        flag = Flag.objects.create(name="f", enabled=True, percentage=50)
        assert evaluate(flag, AnonymousUser()) is False

    def test_a_fully_enabled_flag_reaches_anonymous_visitors(self) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=100)
        assert evaluate(flag, AnonymousUser()) is True

    def test_no_user_at_all_behaves_like_anonymous(self) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=50)
        assert evaluate(flag, None) is False


class TestSubject:
    def test_the_subject_is_the_primary_key_not_the_username(self, user: User) -> None:
        """A rename must not move somebody between buckets mid-rollout."""
        assert subject_of(user) == str(user.pk)
        user.username = "renamed"
        user.save()
        assert subject_of(user) == str(user.pk)

    def test_an_anonymous_user_has_no_subject(self) -> None:
        assert subject_of(AnonymousUser()) is None
        assert subject_of(None) is None


class TestPercentage:
    def test_the_same_user_gets_a_stable_answer(self, user: User) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=50)
        assert len({evaluate(flag, user) for _ in range(50)}) == 1

    def test_raising_the_percentage_never_takes_it_away(
        self, django_user_model: type[User]
    ) -> None:
        users = [django_user_model.objects.create_user(f"u{n}") for n in range(60)]
        flag = Flag.objects.create(name="f", enabled=True, percentage=0)
        seen: set[int] = set()
        for percentage in (10, 30, 60, 100):
            flag.percentage = percentage
            now = {u.pk for u in users if evaluate(flag, u)}
            assert seen <= now, f"someone lost the feature at {percentage}%"
            seen = now
