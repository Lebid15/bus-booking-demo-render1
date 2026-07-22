from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.models import UUIDPrimaryKeyModel
from organizations.models import Office


class PolicyTemplate(UUIDPrimaryKeyModel):
    class PolicyType(models.TextChoices):
        CANCELLATION = "cancellation", "Cancellation"
        PAYMENT = "payment", "Payment"
        BOARDING = "boarding", "Boarding"
        BAGGAGE = "baggage", "Baggage"
        TERMS = "terms", "Terms"
        PRIVACY = "privacy", "Privacy"

    class OwnerScope(models.TextChoices):
        PLATFORM = "platform", "Platform"
        OFFICE = "office", "Office"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    code = models.CharField(max_length=80, unique=True)
    policy_type = models.CharField(max_length=40, choices=PolicyType.choices)
    owner_scope = models.CharField(max_length=20, choices=OwnerScope.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "policy_templates"
        ordering = ["code"]


class PolicyVersion(UUIDPrimaryKeyModel):
    template = models.ForeignKey(PolicyTemplate, on_delete=models.RESTRICT, related_name="versions")
    office = models.ForeignKey(
        Office,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="policy_versions",
    )
    version_no = models.PositiveIntegerField()
    language = models.CharField(max_length=5, default="ar")
    title = models.CharField(max_length=200)
    content_markdown = models.TextField()
    rules_json = models.JSONField(default=dict)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    content_sha256 = models.CharField(max_length=64)

    class Meta:
        db_table = "policy_versions"
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gt=models.F("effective_from")),
                name="ck_policy_version_window",
            ),
            models.UniqueConstraint(
                fields=["template", "office", "version_no", "language"],
                condition=Q(office__isnull=False),
                name="uq_office_policy_version",
            ),
            models.UniqueConstraint(
                fields=["template", "version_no", "language"],
                condition=Q(office__isnull=True),
                name="uq_platform_policy_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["template", "office", "effective_from"],
                name="ix_policy_effective",
            )
        ]
        ordering = ["template__code", "-version_no"]


class PolicyAcceptance(UUIDPrimaryKeyModel):
    class SubjectType(models.TextChoices):
        USER = "user", "User"
        OFFICE = "office", "Office"
        BOOKING = "booking", "Booking"

    policy_version = models.ForeignKey(
        PolicyVersion,
        on_delete=models.RESTRICT,
        related_name="acceptances",
    )
    subject_type = models.CharField(max_length=20, choices=SubjectType.choices)
    subject_id = models.UUIDField()
    accepted_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="policy_acceptances",
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_hash = models.BinaryField(null=True, blank=True)
    user_agent_hash = models.BinaryField(null=True, blank=True)

    class Meta:
        db_table = "policy_acceptances"
        constraints = [
            models.UniqueConstraint(
                fields=["policy_version", "subject_type", "subject_id"],
                name="uq_policy_acceptance_subject",
            )
        ]


class ConfigurationValue(UUIDPrimaryKeyModel):
    class ScopeType(models.TextChoices):
        PLATFORM = "platform", "Platform"
        OFFICE = "office", "Office"
        BRANCH = "branch", "Branch"
        ROUTE = "route", "Route"
        TRIP = "trip", "Trip"

    class ValueType(models.TextChoices):
        BOOLEAN = "boolean", "Boolean"
        INTEGER = "integer", "Integer"
        DECIMAL = "decimal", "Decimal"
        STRING = "string", "String"
        DURATION = "duration", "Duration"
        OBJECT = "object", "Object"
        LIST = "list", "List"

    scope_type = models.CharField(max_length=20, choices=ScopeType.choices)
    scope_id = models.UUIDField(null=True, blank=True)
    key = models.CharField(max_length=120)
    value_json = models.JSONField()
    value_type = models.CharField(max_length=20, choices=ValueType.choices)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_to = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_configuration_values",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="approved_configuration_values",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=240)

    class Meta:
        db_table = "configuration_values"
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gt=models.F("effective_from")),
                name="ck_configuration_window",
            ),
            models.CheckConstraint(
                condition=(
                    Q(scope_type="platform", scope_id__isnull=True)
                    | (~Q(scope_type="platform") & Q(scope_id__isnull=False))
                ),
                name="ck_platform_configuration_scope",
            ),
            models.UniqueConstraint(
                fields=["scope_type", "key", "effective_from"],
                condition=Q(scope_type="platform"),
                name="uq_platform_config_time",
            ),
            models.UniqueConstraint(
                fields=["scope_type", "scope_id", "key", "effective_from"],
                condition=~Q(scope_type="platform"),
                name="uq_scoped_config_time",
            ),
        ]
        indexes = [
            models.Index(fields=["scope_type", "scope_id", "key", "effective_from"], name="ix_config_effective")
        ]
        ordering = ["key", "-effective_from"]
