from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def identity_deployment_checks(app_configs, **kwargs):  # type: ignore[no-untyped-def]
    del app_configs, kwargs
    if str(getattr(settings, "APP_ENV", "local")).lower() != "production":
        return []
    errors = []
    if getattr(settings, "DEMO_MODE", False):
        errors.append(
            Error(
                "Demo mode is enabled in production.",
                hint="Set DEMO_MODE=false before any production deployment.",
                id="identity.E002",
            )
        )
    if getattr(settings, "PLATFORM_RBAC_LEGACY_ADMIN_FALLBACK", True):
        errors.extend([
            Error(
                "Legacy platform administrator permission fallback is enabled in production.",
                hint=(
                    "Assign explicit platform roles to every staff account and set "
                    "PLATFORM_RBAC_LEGACY_ADMIN_FALLBACK=false."
                ),
                id="identity.E001",
            )
        ])
    return errors
