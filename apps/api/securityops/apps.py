from django.apps import AppConfig


class SecurityOpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "securityops"

    def ready(self) -> None:
        from securityops import checks  # noqa: F401
