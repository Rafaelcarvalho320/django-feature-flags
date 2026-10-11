"""The admin screen, which is the whole point of a database-backed flag.

Toggling from the admin is why these live in a table instead of in settings: a
deploy is not an acceptable unit of "turn this off", and during an incident the
person who needs the switch is rarely the person who can ship.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html

from feature_flags.models import Flag

if TYPE_CHECKING:
    # Subscripted for the type checker only: doing it at runtime needs
    # django-stubs-ext's monkeypatch, which a reusable app cannot assume the
    # installing project calls.
    _ModelAdminBase = admin.ModelAdmin[Flag]
else:
    _ModelAdminBase = admin.ModelAdmin


@admin.register(Flag)
class FlagAdmin(_ModelAdminBase):
    list_display = ["name", "state", "percentage", "window", "updated_at"]
    list_filter = ["enabled", "staff_only"]
    search_fields = ["name", "description"]
    filter_horizontal = ["users", "groups"]
    readonly_fields = ["created_at", "updated_at"]
    actions = ["turn_on", "turn_off"]
    fieldsets = [
        (None, {"fields": ["name", "description", "enabled"]}),
        (
            "Targeting",
            {
                "fields": ["percentage", "users", "groups", "staff_only"],
                "description": (
                    "Evaluated in order: the master switch, then the window, "
                    "then staff_only as a gate, then the allowlists, then the "
                    "percentage. An allowlisted user sees the feature whatever "
                    "their bucket."
                ),
            },
        ),
        ("Window", {"fields": ["starts_at", "ends_at"], "classes": ["collapse"]}),
        (
            "Timestamps",
            {"fields": ["created_at", "updated_at"], "classes": ["collapse"]},
        ),
    ]

    @admin.display(description="state", ordering="enabled")
    def state(self, obj: Flag) -> str:
        if not obj.enabled:
            return "off"
        if not obj.within_window:
            return "off (outside window)"
        if obj.is_everyone:
            return "on for everyone"
        parts = []
        if obj.staff_only:
            parts.append("staff only")
        if obj.percentage:
            parts.append(f"{obj.percentage}%")
        if obj.users.exists() or obj.groups.exists():
            parts.append("allowlist")
        return "on: " + ", ".join(parts) if parts else "on for nobody yet"

    @admin.display(description="window")
    def window(self, obj: Flag) -> str:
        if not obj.starts_at and not obj.ends_at:
            return "—"
        start = obj.starts_at.date().isoformat() if obj.starts_at else "…"
        end = obj.ends_at.date().isoformat() if obj.ends_at else "…"
        return format_html("{} → {}", start, end)

    @admin.action(description="Turn selected flags on (master switch)")
    def turn_on(self, request: HttpRequest, queryset: QuerySet[Flag]) -> None:
        self._toggle(request, queryset, True)

    @admin.action(description="Turn selected flags off (master switch)")
    def turn_off(self, request: HttpRequest, queryset: QuerySet[Flag]) -> None:
        self._toggle(request, queryset, False)

    def _toggle(
        self, request: HttpRequest, queryset: QuerySet[Flag], enabled: bool
    ) -> None:
        # Saved one at a time, not with queryset.update(): a bulk update sends
        # no post_save signal, so the cache would keep serving the old answer
        # and the action would look like it did nothing.
        affected = 0
        for flag in queryset:
            if flag.enabled != enabled:
                flag.enabled = enabled
                flag.save(update_fields=["enabled", "updated_at"])
                affected += 1
        self.message_user(
            request,
            f"{affected} flag(s) turned {'on' if enabled else 'off'}.",
            messages.SUCCESS,
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet[Flag]:
        # The list view calls users.exists() and groups.exists() per row, so
        # prefetching turns 2N queries into 2.
        return super().get_queryset(request).prefetch_related("users", "groups")

    def save_model(
        self, request: HttpRequest, obj: Flag, form: Any, change: bool
    ) -> None:
        super().save_model(request, obj, form, change)
        if obj.enabled and obj.percentage == 0 and not obj.users_will_see():
            self.message_user(
                request,
                f"{obj.name} is enabled but nobody matches it yet: the "
                "percentage is 0 and there is no allowlist.",
                messages.WARNING,
            )
