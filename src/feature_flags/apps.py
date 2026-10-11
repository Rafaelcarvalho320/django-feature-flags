from django.apps import AppConfig


class FeatureFlagsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "feature_flags"
    verbose_name = "Feature flags"

    def ready(self) -> None:
        # Imported for its signal receivers, which clear the cache when a flag
        # changes. Inside ready() because models are only importable here.
        from feature_flags import cache  # noqa: F401
