"""The flag table.

One row per flag, with every targeting rule on it. A flag is read on more or
less every request, so the shape is chosen for a single cheap read rather than
for normalisation: one row, no joins except the explicit allowlists.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Flag(models.Model):
    """A single feature flag.

    The rules are evaluated in a fixed order, documented on
    :func:`feature_flags.evaluate.evaluate`. They are deliberately all on one
    model: a flag whose state is spread over four tables is a flag nobody can
    answer questions about in an incident.
    """

    name = models.SlugField(
        unique=True,
        help_text="The key used in code: flag_is_active(request, 'new-checkout').",
    )
    description = models.TextField(
        blank=True,
        help_text="What this flag guards, and when it can be removed. "
        "A flag with no removal condition becomes permanent.",
    )

    # The master switch. Off means off, whatever the other rules say.
    enabled = models.BooleanField(
        default=False,
        help_text="Master switch. Everything below is ignored while this is off.",
    )

    percentage = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Sticky rollout: the same user always gets the same answer. "
        "0 means nobody by percentage, 100 means everyone.",
    )

    # Allowlists win over the percentage, so the team can see a feature before
    # anybody else regardless of where their bucket fell.
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="feature_flags",
        help_text="These users always see it while the flag is enabled.",
    )
    groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="feature_flags",
        help_text="Members of these groups always see it.",
    )

    staff_only = models.BooleanField(
        default=False,
        help_text="Restrict to staff. Combines with the rules above as a gate: "
        "a non-staff user is refused even if listed.",
    )

    starts_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Before this moment the flag is off. Blank means no start.",
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="After this moment the flag is off. Blank means no end.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError(
                {"ends_at": "The end of the window must come after its start."}
            )

    @property
    def within_window(self) -> bool:
        """Whether now falls inside the configured window."""
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        return not (self.ends_at and now > self.ends_at)

    def users_will_see(self) -> bool:
        """Whether anybody at all matches this flag as configured.

        Used by the admin to warn about the easiest mistake with a flag: it is
        enabled, so it looks live, but the percentage is still zero and there
        is no allowlist, so nobody is seeing anything.
        """
        return bool(self.percentage) or self.users.exists() or self.groups.exists()

    @property
    def is_everyone(self) -> bool:
        """A flag that is simply on for everybody, with no targeting left."""
        return (
            self.enabled
            and self.percentage >= 100
            and not self.staff_only
            and self.within_window
        )
