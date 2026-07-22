from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q

from common.ids import generate_public_id


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(
        self,
        *,
        full_name: str,
        password: str | None = None,
        email: str | None = None,
        phone_e164: str | None = None,
        **extra_fields: Any,
    ) -> User:
        if not email and not phone_e164:
            raise ValueError("Email or phone is required")
        user = self.model(
            full_name=full_name.strip(),
            email=self.normalize_email(email).lower() if email else None,
            phone_e164=phone_e164,
            **extra_fields,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, *, full_name: str, password: str, email: str, **extra_fields: Any) -> User:
        extra_fields.setdefault("is_platform_staff", True)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        return self.create_user(full_name=full_name, password=password, email=email, **extra_fields)


class User(AbstractBaseUser):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DISABLED = "disabled", "Disabled"
        DELETED = "deleted", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    email = models.EmailField(null=True, blank=True)
    phone_e164 = models.CharField(max_length=20, null=True, blank=True)
    last_login = None
    password = models.CharField(  # type: ignore[assignment]
        max_length=128, db_column="password_hash", null=True, blank=True
    )
    full_name = models.CharField(max_length=160)
    preferred_language = models.CharField(max_length=5, default="ar")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ACTIVE)
    is_platform_staff = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "public_id"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"
        constraints = [
            models.CheckConstraint(
                condition=Q(email__isnull=False) | Q(phone_e164__isnull=False),
                name="ck_user_has_identifier",
            ),
            models.UniqueConstraint(fields=["email"], condition=Q(email__isnull=False), name="uq_users_email"),
            models.UniqueConstraint(
                fields=["phone_e164"], condition=Q(phone_e164__isnull=False), name="uq_users_phone"
            ),
        ]

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return self.status == self.Status.ACTIVE

    @property
    def is_staff(self) -> bool:
        return self.is_platform_staff

    def __str__(self) -> str:
        return self.full_name


class CustomerProfile(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    user = models.OneToOneField(User, primary_key=True, on_delete=models.RESTRICT, related_name="customer_profile")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=12, choices=Gender.choices, null=True, blank=True)
    nationality_code = models.CharField(max_length=2, null=True, blank=True)
    marketing_consent = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "customer_profiles"


class UserDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.RESTRICT, related_name="devices")
    device_fingerprint_hash = models.BinaryField()
    label = models.CharField(max_length=120, null=True, blank=True)
    trusted_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_devices"
        constraints = [
            models.UniqueConstraint(fields=["user", "device_fingerprint_hash"], name="uq_user_device_fingerprint")
        ]


class ActiveSessionManager(models.Manager["UserSession"]):
    def get_queryset(self) -> models.QuerySet[UserSession]:
        return super().get_queryset().filter(revoked_at__isnull=True)


class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.RESTRICT, related_name="sessions")
    token_hash = models.BinaryField(unique=True)
    device = models.ForeignKey(
        UserDevice,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="sessions",
    )
    ip_hash = models.BinaryField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    expires_at = models.DateTimeField()
    mfa_verified_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    active = ActiveSessionManager()

    class Meta:
        db_table = "user_sessions"
        indexes = [models.Index(fields=["user", "revoked_at", "expires_at"], name="ix_user_sessions_active")]


class MfaMethod(models.Model):
    class MethodType(models.TextChoices):
        TOTP = "totp", "TOTP"
        WEBAUTHN = "webauthn", "WebAuthn"
        RECOVERY = "recovery", "Recovery"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.RESTRICT, related_name="mfa_methods")
    method_type = models.CharField(max_length=20, choices=MethodType.choices)
    secret_ciphertext = models.BinaryField(null=True, blank=True)
    credential_id = models.BinaryField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mfa_methods"


class Role(models.Model):
    class ScopeType(models.TextChoices):
        PLATFORM = "platform", "Platform"
        OFFICE = "office", "Office"
        BRANCH = "branch", "Branch"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=80, unique=True)
    scope_type = models.CharField(max_length=20, choices=ScopeType.choices)
    name_ar = models.CharField(max_length=120)
    is_system = models.BooleanField(default=True)
    permissions = models.ManyToManyField(  # type: ignore[var-annotated]
        "Permission", through="RolePermission", related_name="roles"
    )

    class Meta:
        db_table = "roles"


class Permission(models.Model):
    class RiskLevel(models.TextChoices):
        NORMAL = "normal", "Normal"
        SENSITIVE = "sensitive", "Sensitive"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=120, unique=True)
    name_ar = models.CharField(max_length=160)
    risk_level = models.CharField(max_length=12, choices=RiskLevel.choices, default=RiskLevel.NORMAL)

    class Meta:
        db_table = "permissions"


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.RESTRICT)
    permission = models.ForeignKey(Permission, on_delete=models.RESTRICT)

    class Meta:
        db_table = "role_permissions"
        constraints = [models.UniqueConstraint(fields=["role", "permission"], name="pk_role_permissions")]


class PlatformRoleAssignment(models.Model):
    """Assign a platform-scoped role to a platform staff user.

    The normative schema defines platform roles and permissions but does not expose a
    staff membership table. This additive table closes that authorization gap while
    keeping the existing role catalog as the source of permission truth.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.RESTRICT, related_name="platform_role_assignments")
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, related_name="platform_assignments")
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="assigned_platform_roles",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "platform_role_assignments"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uq_platform_user_role"),
        ]
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="ix_platform_role_active"),
        ]
