from __future__ import annotations

import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
APP_ENV = os.getenv("APP_ENV", "local")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


DEMO_MODE = env_bool("DEMO_MODE", False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "common",
    "identity",
    "organizations",
    "geography",
    "fleet",
    "policies",
    "trips",
    "bookings",
    "tickets",
    "boarding",
    "support",
    "payments",
    "finance",
    "auditlog",
    "adminops",
    "notifications",
    "securityops",
    "subscriptions",
    "continuity",
]

MIDDLEWARE = [
    "common.middleware.RequestIDMiddleware",
    "continuity.middleware.ContinuityWriteGuardMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES: list[dict[str, object]] = []
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")
DATABASE_CONN_MAX_AGE = int(os.getenv("DATABASE_CONN_MAX_AGE", "0"))
DATABASE_CONN_HEALTH_CHECKS = env_bool("DATABASE_CONN_HEALTH_CHECKS", True)
DATABASES: dict[str, dict[str, Any]]
if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
    from urllib.parse import urlparse

    parsed = urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username,
            "PASSWORD": parsed.password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
            # Persistent connections can exhaust PostgreSQL under ASGI because
            # each sync worker thread owns its own connection. Keep request
            # connections short-lived by default; use PgBouncer or an explicit
            # environment override for a measured deployment.
            "CONN_MAX_AGE": DATABASE_CONN_MAX_AGE,
            "CONN_HEALTH_CHECKS": DATABASE_CONN_HEALTH_CHECKS,
            "OPTIONS": {"connect_timeout": 5},
        }
    }
else:
    sqlite_name = DATABASE_URL.removeprefix("sqlite:///")
    if not sqlite_name:
        sqlite_name = "db.sqlite3"
    sqlite_path = Path(sqlite_name)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(sqlite_path if sqlite_path.is_absolute() else BASE_DIR / sqlite_path),
            "CONN_MAX_AGE": DATABASE_CONN_MAX_AGE,
            "CONN_HEALTH_CHECKS": DATABASE_CONN_HEALTH_CHECKS,
        }
    }

AUTH_USER_MODEL = "identity.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ar"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"

REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "bus-booking-local",
        }
    }

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["identity.authentication.SessionBearerAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,  # nosec B105 - DRF setting, not a password
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Bus Booking Platform API",
    "VERSION": "4.0.0-g19-launch-readiness",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "BookingPaymentMethod": "payments.models.PaymentIntent.MethodType",
        "PayoutMethodType": "organizations.models.OfficePayoutAccount.MethodType",
        "OfficeMembershipStatus": "organizations.models.OfficeMembership.Status",
        "SeatLayoutStatus": "fleet.models.SeatLayout.Status",
        "VehicleStatus": "fleet.models.Vehicle.Status",
        "ActiveInactiveStatus": "geography.models.Location.Status",
        "ViolationSeverity": ["P0", "P1", "P2", "P3", "P4"],
        "DriverStatus": "fleet.models.Driver.Status",
    },
}

CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()
]

JWT_SIGNING_KEY = os.getenv("JWT_SIGNING_KEY", SECRET_KEY)
JWT_ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "900"))
SESSION_MAX_TTL_SECONDS = int(os.getenv("SESSION_MAX_TTL_SECONDS", "2592000"))
MFA_CHALLENGE_TTL_SECONDS = int(os.getenv("MFA_CHALLENGE_TTL_SECONDS", "300"))
REGISTRATION_CHALLENGE_TTL_SECONDS = int(os.getenv("REGISTRATION_CHALLENGE_TTL_SECONDS", "600"))
DEV_VERIFICATION_CODE = os.getenv("DEV_VERIFICATION_CODE", "123456")
MFA_ENCRYPTION_KEY = os.getenv("MFA_ENCRYPTION_KEY", "")
PLATFORM_RBAC_LEGACY_ADMIN_FALLBACK = env_bool("PLATFORM_RBAC_LEGACY_ADMIN_FALLBACK", True)
LOGIN_RATE_LIMIT_BASE_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_BASE_SECONDS", "30"))
LOGIN_RATE_LIMIT_THRESHOLD = int(os.getenv("LOGIN_RATE_LIMIT_THRESHOLD", "5"))

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL or "memory://")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "cache+memory://")
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_BEAT_SCHEDULE = {
    "open-due-trip-bookings": {
        "task": "trips.open_due_bookings",
        "schedule": 60.0,
    },
    "expire-seat-holds": {
        "task": "bookings.expire_seat_holds",
        "schedule": 30.0,
    },
    "expire-unpaid-bookings": {
        "task": "payments.expire_due_unpaid_bookings",
        "schedule": 30.0,
    },
    "process-received-payment-webhooks": {
        "task": "payments.process_received_webhooks",
        "schedule": 5.0,
    },
    "mark-due-no-shows": {
        "task": "boarding.mark_due_no_shows",
        "schedule": 30.0,
    },
    "escalate-overdue-support-cases": {
        "task": "support.escalate_overdue_cases",
        "schedule": 30.0,
    },
    "dispatch-notification-events": {
        "task": "notifications.dispatch_outbox_events",
        "schedule": 5.0,
    },
    "deliver-due-notifications": {
        "task": "notifications.deliver_due_notifications",
        "schedule": 5.0,
    },
    "process-retention-requests": {
        "task": "securityops.process_retention_requests",
        "schedule": 3600.0,
    },
    "process-due-subscriptions": {
        "task": "subscriptions.process_due_subscriptions",
        "schedule": 300.0,
    },
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
X_FRAME_OPTIONS = "DENY"

OFFICE_VERIFICATION_REQUIRED_DOCUMENT_TYPES = os.getenv(
    "OFFICE_VERIFICATION_REQUIRED_DOCUMENT_TYPES",
    "commercial_registration,operating_license,representative_identity",
)

PAYOUT_ACCOUNT_COOLING_HOURS = int(os.getenv("PAYOUT_ACCOUNT_COOLING_HOURS", "24"))
SENSITIVE_MFA_MAX_AGE_SECONDS = int(os.getenv("SENSITIVE_MFA_MAX_AGE_SECONDS", "900"))

TRIP_REQUIRED_POLICY_TYPES = os.getenv("TRIP_REQUIRED_POLICY_TYPES", "cancellation,payment,boarding")
TRIP_DEFAULT_DURATION_HOURS = int(os.getenv("TRIP_DEFAULT_DURATION_HOURS", "8"))
TRIP_RESOURCE_TURNAROUND_MINUTES = int(os.getenv("TRIP_RESOURCE_TURNAROUND_MINUTES", "60"))
TRIP_MATERIAL_CHANGE_MINUTES = int(os.getenv("TRIP_MATERIAL_CHANGE_MINUTES", "30"))
TRIP_CHANGE_RESPONSE_HOURS = int(os.getenv("TRIP_CHANGE_RESPONSE_HOURS", "24"))

SEAT_HOLD_TTL_SECONDS = int(os.getenv("SEAT_HOLD_TTL_SECONDS", "600"))
PUBLIC_HOLD_RATE_LIMIT = int(os.getenv("PUBLIC_HOLD_RATE_LIMIT", "20"))
PUBLIC_HOLD_RATE_WINDOW_SECONDS = int(os.getenv("PUBLIC_HOLD_RATE_WINDOW_SECONDS", "60"))
BOOKING_MANAGE_TOKEN_KEY = os.getenv("BOOKING_MANAGE_TOKEN_KEY", SECRET_KEY)
PUBLIC_BOOKING_RATE_LIMIT = int(os.getenv("PUBLIC_BOOKING_RATE_LIMIT", "12"))
PUBLIC_BOOKING_RATE_WINDOW_SECONDS = int(os.getenv("PUBLIC_BOOKING_RATE_WINDOW_SECONDS", "60"))

TICKET_QR_SIGNING_KEY = os.getenv("TICKET_QR_SIGNING_KEY", SECRET_KEY)
PUBLIC_BOOKING_LOOKUP_RATE_LIMIT = int(os.getenv("PUBLIC_BOOKING_LOOKUP_RATE_LIMIT", "8"))
PUBLIC_BOOKING_LOOKUP_RATE_WINDOW_SECONDS = int(os.getenv("PUBLIC_BOOKING_LOOKUP_RATE_WINDOW_SECONDS", "300"))


PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "unsafe-local-payment-webhook-secret")
ELECTRONIC_PAYMENT_ENABLED = env_bool("ELECTRONIC_PAYMENT_ENABLED", False)
DEFAULT_PAYMENT_PROVIDER_CODE = os.getenv("DEFAULT_PAYMENT_PROVIDER_CODE", "mock")
PAYMENT_PROVIDER_CHECKOUT_BASE_URL = os.getenv(
    "PAYMENT_PROVIDER_CHECKOUT_BASE_URL", "http://localhost:3000/mock-payment"
)

CANCELLATION_QUOTE_SIGNING_KEY = os.getenv("CANCELLATION_QUOTE_SIGNING_KEY", SECRET_KEY)
CANCELLATION_QUOTE_TTL_SECONDS = int(os.getenv("CANCELLATION_QUOTE_TTL_SECONDS", "600"))
REFUND_DUAL_APPROVAL_THRESHOLD = os.getenv("REFUND_DUAL_APPROVAL_THRESHOLD", "500000.00")

BOARDING_OFFLINE_ENCRYPTION_KEY = os.getenv("BOARDING_OFFLINE_ENCRYPTION_KEY", SECRET_KEY)
BOARDING_OFFLINE_SIGNING_KEY = os.getenv("BOARDING_OFFLINE_SIGNING_KEY", SECRET_KEY)
OFFLINE_BOARDING_PACKAGE_TTL_SECONDS = int(os.getenv("OFFLINE_BOARDING_PACKAGE_TTL_SECONDS", "21600"))

SUPPORT_P0_SLA_MINUTES = int(os.getenv("SUPPORT_P0_SLA_MINUTES", "5"))
SUPPORT_P1_SLA_MINUTES = int(os.getenv("SUPPORT_P1_SLA_MINUTES", "15"))
SUPPORT_P2_SLA_MINUTES = int(os.getenv("SUPPORT_P2_SLA_MINUTES", "60"))
SUPPORT_P3_SLA_MINUTES = int(os.getenv("SUPPORT_P3_SLA_MINUTES", "240"))
SUPPORT_P4_SLA_MINUTES = int(os.getenv("SUPPORT_P4_SLA_MINUTES", "1440"))

NOTIFICATION_MAX_ATTEMPTS = int(os.getenv("NOTIFICATION_MAX_ATTEMPTS", "4"))
NOTIFICATION_RETRY_BASE_SECONDS = int(os.getenv("NOTIFICATION_RETRY_BASE_SECONDS", "30"))
NOTIFICATION_RETRY_MAX_SECONDS = int(os.getenv("NOTIFICATION_RETRY_MAX_SECONDS", "3600"))
NOTIFICATION_FORCE_FAILURE_CHANNELS = os.getenv("NOTIFICATION_FORCE_FAILURE_CHANNELS", "")
NOTIFICATION_ESCALATION_WINDOW_HOURS = int(os.getenv("NOTIFICATION_ESCALATION_WINDOW_HOURS", "24"))


PRIVATE_UPLOAD_BASE_URL = os.getenv("PRIVATE_UPLOAD_BASE_URL", "https://upload.invalid")
FILE_SCANNER_BACKEND = os.getenv("FILE_SCANNER_BACKEND", "")
FILE_SCAN_MOCK_RESULT = os.getenv("FILE_SCAN_MOCK_RESULT", "clean")
FILE_RETENTION_DAYS = int(os.getenv("FILE_RETENTION_DAYS", "365"))
RISK_STEP_UP_THRESHOLD = os.getenv("RISK_STEP_UP_THRESHOLD", "50")
RISK_MANUAL_REVIEW_THRESHOLD = os.getenv("RISK_MANUAL_REVIEW_THRESHOLD", "70")
RISK_BLOCK_THRESHOLD = os.getenv("RISK_BLOCK_THRESHOLD", "90")
RISK_STEP_UP_CODE = os.getenv("RISK_STEP_UP_CODE", "123456")
RISK_STEP_UP_SIGNING_KEY = os.getenv("RISK_STEP_UP_SIGNING_KEY", SECRET_KEY)

SUBSCRIPTION_ENFORCEMENT_ENABLED = env_bool("SUBSCRIPTION_ENFORCEMENT_ENABLED", True)
SUBSCRIPTION_INVOICE_DUE_DAYS = int(os.getenv("SUBSCRIPTION_INVOICE_DUE_DAYS", "7"))
SUBSCRIPTION_GRACE_DAYS = int(os.getenv("SUBSCRIPTION_GRACE_DAYS", "7"))
