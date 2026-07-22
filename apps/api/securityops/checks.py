from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.utils.module_loading import import_string


@register(Tags.security, deploy=True)
def securityops_deployment_checks(app_configs, **kwargs):  # type: ignore[no-untyped-def]
    del app_configs, kwargs
    if str(getattr(settings, "APP_ENV", "local")).lower() != "production":
        return []

    errors: list[Error] = []
    upload_url = str(getattr(settings, "PRIVATE_UPLOAD_BASE_URL", "")).strip()
    parsed = urlparse(upload_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.netloc.endswith(".invalid"):
        errors.append(
            Error(
                "Private upload storage must use a real HTTPS endpoint in production.",
                hint="Set PRIVATE_UPLOAD_BASE_URL to the private object-storage upload endpoint.",
                id="securityops.E001",
            )
        )

    scanner_backend = str(getattr(settings, "FILE_SCANNER_BACKEND", "")).strip()
    if not scanner_backend:
        errors.append(
            Error(
                "A malware scanner backend is required in production.",
                hint="Set FILE_SCANNER_BACKEND to an importable scanner callable.",
                id="securityops.E002",
            )
        )
    else:
        try:
            scanner = import_string(scanner_backend)
            if not callable(scanner):
                raise TypeError("scanner backend is not callable")
        except (ImportError, AttributeError, TypeError) as exc:
            errors.append(
                Error(
                    "FILE_SCANNER_BACKEND is not an importable callable.",
                    hint=str(exc),
                    id="securityops.E003",
                )
            )

    if str(getattr(settings, "RISK_STEP_UP_CODE", "123456")) == "123456":
        errors.append(
            Error(
                "The development risk step-up code is enabled in production.",
                hint="Configure a non-default Sandbox code now and replace it with a real OTP provider before launch.",
                id="securityops.E004",
            )
        )
    return errors
