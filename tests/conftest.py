"""Fixtures."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, User
from django.core.cache import cache

from feature_flags.models import Flag


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    """The flag cache is process-wide, so it has to be cleared between tests.

    Autouse because forgetting it once makes an unrelated test fail in a way
    that looks like a caching bug in the library rather than in the suite.
    """
    cache.clear()


@pytest.fixture
def flag(db: None) -> Flag:
    return Flag.objects.create(name="new-checkout", enabled=True, percentage=100)


@pytest.fixture
def off_flag(db: None) -> Flag:
    return Flag.objects.create(name="new-checkout", enabled=False, percentage=100)


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user("ana", password="password-for-tests")


@pytest.fixture
def other_user(db: None) -> User:
    return User.objects.create_user("bruno", password="password-for-tests")


@pytest.fixture
def staff_user(db: None) -> User:
    return User.objects.create_user(
        "carla", password="password-for-tests", is_staff=True
    )


@pytest.fixture
def beta_group(db: None) -> Group:
    return Group.objects.create(name="beta")
