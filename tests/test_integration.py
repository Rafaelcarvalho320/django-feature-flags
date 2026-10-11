"""The decorator, the template tag and the admin, through real requests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from feature_flags.models import Flag

pytestmark = pytest.mark.django_db


class TestDecorator:
    def test_the_view_works_when_the_flag_is_on(
        self, flag: Flag, client: Client
    ) -> None:
        response = client.get("/guarded/")
        assert response.status_code == 200
        assert b"the new checkout" in response.content

    def test_it_is_a_404_when_the_flag_is_off(
        self, off_flag: Flag, client: Client
    ) -> None:
        """A 404, not a 403. A 403 says "this exists and you may not have it",
        which tells anybody probing that the feature is there."""
        assert client.get("/guarded/").status_code == 404

    def test_a_missing_flag_is_also_a_404(self, client: Client, db: None) -> None:
        assert client.get("/guarded/").status_code == 404

    def test_it_can_redirect_instead(self, off_flag: Flag, client: Client) -> None:
        response = client.get("/guarded-redirect/")
        assert response.status_code == 302
        assert response["Location"] == "/old/"

    def test_the_decorator_keeps_the_view_identity(self) -> None:
        """functools.wraps, so Django's own machinery and any further
        decorator still see the real view."""
        from tests.testapp.views import guarded

        assert guarded.__name__ == "guarded"

    def test_it_respects_the_user_not_just_the_flag(
        self, client: Client, user: User, db: None
    ) -> None:
        flag = Flag.objects.create(name="new-checkout", enabled=True, percentage=0)
        assert client.get("/guarded/").status_code == 404

        flag.users.add(user)
        client.force_login(user)
        assert client.get("/guarded/").status_code == 200


class TestTemplate:
    def test_both_spellings_agree_when_on(self, flag: Flag, client: Client) -> None:
        body = client.get("/rendered/").content.decode()
        assert "tag:on" in body
        assert "filter:on" in body

    def test_both_spellings_agree_when_off(
        self, off_flag: Flag, client: Client
    ) -> None:
        body = client.get("/rendered/").content.decode()
        assert "tag:off" in body
        assert "filter:off" in body

    def test_a_template_without_a_request_does_not_raise(self, db: None) -> None:
        """An email rendered off-request should fall back, not break."""
        from django.template import Context, Template

        rendered = Template(
            '{% load feature_flags %}{% flag "anything" as on %}'
            "{% if on %}yes{% else %}no{% endif %}"
        ).render(Context({}))
        assert rendered == "no"


class TestAdmin:
    @pytest.fixture
    def admin_client_for(self, client: Client, db: None) -> Client:
        User.objects.create_superuser("root", "root@example.com", "password-x")
        client.force_login(User.objects.get(username="root"))
        return client

    def test_the_list_shows_a_readable_state(
        self, admin_client_for: Client, flag: Flag
    ) -> None:
        body = admin_client_for.get(
            reverse("admin:feature_flags_flag_changelist")
        ).content.decode()
        assert "on for everyone" in body

    def test_the_bulk_action_takes_effect_immediately(
        self, admin_client_for: Client, flag: Flag
    ) -> None:
        """Saved one at a time, not with queryset.update(): a bulk update
        sends no post_save signal, so the cache would keep the old answer and
        the action would look like it did nothing."""
        from feature_flags.api import flag_is_active

        assert flag_is_active(None, "new-checkout") is True
        admin_client_for.post(
            reverse("admin:feature_flags_flag_changelist"),
            data={
                "action": "turn_off",
                "_selected_action": [flag.pk],
            },
        )
        flag.refresh_from_db()
        assert flag.enabled is False
        assert flag_is_active(None, "new-checkout") is False

    def test_turning_it_back_on(self, admin_client_for: Client, off_flag: Flag) -> None:
        from feature_flags.api import flag_is_active

        admin_client_for.post(
            reverse("admin:feature_flags_flag_changelist"),
            data={"action": "turn_on", "_selected_action": [off_flag.pk]},
        )
        assert flag_is_active(None, "new-checkout") is True

    def test_the_listing_does_not_scale_queries_with_rows(
        self, admin_client_for: Client, db: None
    ) -> None:
        """The state column asks about the allowlists per row, so without
        prefetching this is 2N queries."""
        for n in range(12):
            Flag.objects.create(name=f"flag-{n}", enabled=True, percentage=50)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            admin_client_for.get(reverse("admin:feature_flags_flag_changelist"))
        assert len(captured) < 20, f"{len(captured)} queries for 12 rows"


class TestModelValidation:
    def test_a_window_that_ends_before_it_starts_is_rejected(self, db: None) -> None:
        from django.core.exceptions import ValidationError
        from django.utils import timezone

        now = timezone.now()
        flag = Flag(
            name="f",
            starts_at=now,
            ends_at=now - timezone.timedelta(hours=1),
        )
        with pytest.raises(ValidationError):
            flag.full_clean()

    def test_a_percentage_above_a_hundred_is_rejected(self, db: None) -> None:
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            Flag(name="f", percentage=101).full_clean()

    def test_users_will_see_warns_about_a_flag_nobody_matches(
        self, db: None, user: User
    ) -> None:
        flag = Flag.objects.create(name="f", enabled=True, percentage=0)
        assert flag.users_will_see() is False
        flag.users.add(user)
        assert flag.users_will_see() is True
