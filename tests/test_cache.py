"""Caching, and the invalidation that makes a toggle take effect."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from feature_flags import cache as flag_cache
from feature_flags.api import flag_is_active
from feature_flags.models import Flag

pytestmark = pytest.mark.django_db


class TestReads:
    def test_repeated_reads_do_not_hit_the_database(
        self, flag: Flag, django_assert_num_queries: object
    ) -> None:
        flag_cache.all_flags()
        with django_assert_num_queries(0):  # type: ignore[operator]
            for _ in range(10):
                flag_cache.get_flag("new-checkout")

    def test_the_whole_set_is_cached_under_one_key(
        self, db: None, django_assert_num_queries: object
    ) -> None:
        """A page checking six flags costs one cache read, not six."""
        for n in range(6):
            Flag.objects.create(name=f"flag-{n}", enabled=True, percentage=100)
        flag_cache.all_flags()
        with django_assert_num_queries(0):  # type: ignore[operator]
            for n in range(6):
                assert flag_cache.get_flag(f"flag-{n}") is not None

    def test_the_cache_can_be_bypassed(self, flag: Flag) -> None:
        assert flag_cache.get_flag("new-checkout", use_cache=False) is not None


class TestInvalidation:
    def test_saving_a_flag_makes_the_change_visible(self, flag: Flag) -> None:
        """The bug most worth a test here: the toggle appeared to do nothing
        because the cache kept serving the old row."""
        assert flag_is_active(None, "new-checkout") is True
        flag.enabled = False
        flag.save()
        assert flag_is_active(None, "new-checkout") is False

    def test_deleting_a_flag_makes_it_off(self, flag: Flag) -> None:
        assert flag_is_active(None, "new-checkout") is True
        flag.delete()
        assert flag_is_active(None, "new-checkout") is False

    def test_creating_a_flag_makes_it_visible(self, db: None) -> None:
        assert flag_is_active(None, "later") is False
        Flag.objects.create(name="later", enabled=True, percentage=100)
        assert flag_is_active(None, "later") is True

    def test_adding_a_user_to_the_allowlist_takes_effect_at_once(
        self, user: User, db: None
    ) -> None:
        """The allowlist lives in a separate table, so saving the flag is not
        involved. Without an m2m_changed receiver this did nothing until the
        timeout expired, which reads as the feature being broken."""
        flag = Flag.objects.create(name="beta", enabled=True, percentage=0)
        from feature_flags.api import flag_is_active_for_user

        assert flag_is_active_for_user(user, "beta") is False
        flag.users.add(user)
        assert flag_is_active_for_user(user, "beta") is True

    def test_removing_a_user_from_the_allowlist_takes_effect_at_once(
        self, user: User, db: None
    ) -> None:
        flag = Flag.objects.create(name="beta", enabled=True, percentage=0)
        flag.users.add(user)
        from feature_flags.api import flag_is_active_for_user

        assert flag_is_active_for_user(user, "beta") is True
        flag.users.remove(user)
        assert flag_is_active_for_user(user, "beta") is False


class TestRequestMemo:
    def test_a_flag_checked_twice_in_one_request_is_evaluated_once(
        self, user: User, rf: object
    ) -> None:
        """A template checking the same flag in three places should not run
        the allowlist queries three times."""
        flag = Flag.objects.create(name="beta", enabled=True, percentage=0)
        flag.users.add(user)
        flag_cache.all_flags()

        request = rf.get("/")  # type: ignore[attr-defined]
        request.user = user

        assert flag_is_active(request, "beta") is True
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            for _ in range(5):
                assert flag_is_active(request, "beta") is True
        assert len(captured) == 0

    def test_the_memo_does_not_cross_requests(self, user: User, rf: object) -> None:
        flag = Flag.objects.create(name="beta", enabled=True, percentage=100)
        first = rf.get("/")  # type: ignore[attr-defined]
        first.user = user
        assert flag_is_active(first, "beta") is True

        flag.enabled = False
        flag.save()

        second = rf.get("/")  # type: ignore[attr-defined]
        second.user = user
        assert flag_is_active(second, "beta") is False
