from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from common.models import OutboxEvent
from geography.models import Location
from identity.models import Role, User
from identity.normalization import normalize_identifier
from organizations.models import (
    Office,
    OfficeBranch,
    OfficeDocument,
    OfficeMembership,
    OfficePayoutAccount,
    VerificationCase,
)


@dataclass(frozen=True)
class OfficeContext:
    membership: OfficeMembership
    permissions: frozenset[str]

    @property
    def office(self):  # type: ignore[no-untyped-def]
        return self.membership.office

    @property
    def branch(self):  # type: ignore[no-untyped-def]
        return self.membership.branch


def resolve_office_context(user) -> OfficeContext:  # type: ignore[no-untyped-def]
    memberships = list(
        OfficeMembership.objects.for_user(user)
        .select_related("office", "office__operator", "branch", "role")
        .prefetch_related("role__permissions")[:2]
    )
    if len(memberships) != 1:
        raise DomainAPIException(
            "TENANT_ACCESS_DENIED",
            details={"reason": "membership_context_unavailable"},
        )
    membership = memberships[0]
    permission_codes = frozenset(membership.role.permissions.values_list("code", flat=True))
    return OfficeContext(membership=membership, permissions=permission_codes)


def require_permission(context: OfficeContext, permission_code: str) -> None:
    if permission_code not in context.permissions:
        raise DomainAPIException("PERMISSION_DENIED")


def _location_for_branch(public_id: str) -> Location:
    location = Location.objects.filter(public_id=public_id, status=Location.Status.ACTIVE).first()
    if location is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "location_id", "reason": "not_found_or_inactive"}],
        )
    if location.location_type not in {
        Location.LocationType.GARAGE,
        Location.LocationType.BOARDING_POINT,
    }:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "location_id", "reason": "branch_requires_operational_point"}],
        )
    return location


@transaction.atomic
def create_branch(
    *, context: OfficeContext, actor: User, request: HttpRequest, data: dict[str, Any]
) -> OfficeBranch:
    from subscriptions.services import require_usage_capacity

    require_usage_capacity(context.office, "branches")
    required = [field for field in ("name", "location_id") if not data.get(field)]
    if required:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": field, "reason": "required"} for field in required],
        )
    location = _location_for_branch(str(data["location_id"]))
    try:
        branch = OfficeBranch.objects.create(
            office=context.office,
            name=str(data["name"]).strip(),
            location=location,
            phone=data.get("phone") or None,
            status=data.get("status", "active"),
            is_primary=bool(data.get("is_primary", False)),
        )
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "branch_name_or_primary_exists"}) from exc
    record_audit(
        action="office.branch.create",
        object_type="office_branch",
        object_id=branch.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"public_id": branch.public_id, "name": branch.name, "location_id": location.public_id},
    )
    return branch


@transaction.atomic
def update_branch(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    branch_id: str,
    data: dict[str, Any],
) -> OfficeBranch:
    branch = (
        OfficeBranch.objects.select_for_update()
        .select_related("location")
        .filter(public_id=branch_id, office=context.office)
        .first()
    )
    if branch is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    supplied_version = data.get("version")
    if supplied_version is None or int(supplied_version) != branch.version:
        raise DomainAPIException(
            "VERSION_CONFLICT",
            details={"current_version": branch.version},
        )
    before = {
        "name": branch.name,
        "phone": branch.phone,
        "status": branch.status,
        "is_primary": branch.is_primary,
        "location_id": branch.location.public_id,
        "version": branch.version,
    }
    if "location_id" in data:
        branch.location = _location_for_branch(str(data["location_id"]))
    for field in ("name", "phone", "status", "is_primary"):
        if field in data:
            value = data[field]
            if field == "phone":
                value = value or None
            setattr(branch, field, value)
    branch.version += 1
    try:
        branch.full_clean()
        branch.save()
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "branch_name_or_primary_exists"}) from exc
    record_audit(
        action="office.branch.update",
        object_type="office_branch",
        object_id=branch.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before=before,
        after={
            "name": branch.name,
            "phone": branch.phone,
            "status": branch.status,
            "is_primary": branch.is_primary,
            "location_id": branch.location.public_id,
            "version": branch.version,
        },
    )
    return branch


def _role_for_office(code: str) -> Role:
    role = Role.objects.filter(code=code, scope_type__in=[Role.ScopeType.OFFICE, Role.ScopeType.BRANCH]).first()
    if role is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "role_code", "reason": "not_found"}],
        )
    return role


def _branch_for_office(office: Office, branch_id: str | None) -> OfficeBranch | None:
    if not branch_id:
        return None
    branch = OfficeBranch.objects.filter(public_id=branch_id, office=office).first()
    if branch is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "branch_id", "reason": "not_found"}],
        )
    return branch


@transaction.atomic
def invite_staff(
    *, context: OfficeContext, actor: User, request: HttpRequest, data: dict[str, Any]
) -> OfficeMembership:
    from subscriptions.services import require_usage_capacity

    require_usage_capacity(context.office, "staff")
    kind, normalized = normalize_identifier(str(data["identifier"]))
    role = _role_for_office(str(data["role_code"]))
    branch = _branch_for_office(context.office, data.get("branch_id"))
    user = User.objects.filter(**{kind: normalized}).first()
    if user is None:
        user_kwargs: dict[str, Any] = {
            "full_name": "موظف مدعو",
            "status": User.Status.DISABLED,
            kind: normalized,
        }
        user = User.objects.create_user(**user_kwargs)
    try:
        membership = OfficeMembership.objects.create(
            user=user,
            office=context.office,
            branch=branch,
            role=role,
            status=OfficeMembership.Status.INVITED,
        )
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "membership_exists"}) from exc
    OutboxEvent.objects.create(
        aggregate_type="office_membership",
        aggregate_id=membership.id,
        event_type="office.staff.invited",
        payload={
            "office_id": str(context.office.id),
            "membership_id": str(membership.id),
            "user_id": str(user.id),
        },
    )
    record_audit(
        action="office.staff.invite",
        object_type="office_membership",
        object_id=membership.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"role": role.code, "branch_id": branch.public_id if branch else None, "status": membership.status},
    )
    return membership


@transaction.atomic
def update_staff(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    membership_id: uuid.UUID,
    data: dict[str, Any],
) -> OfficeMembership:
    membership = (
        OfficeMembership.objects.select_for_update()
        .select_related("user", "role", "branch")
        .filter(id=membership_id, office=context.office)
        .first()
    )
    if membership is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if membership.user_id == actor.id and data.get("status") in {
        OfficeMembership.Status.SUSPENDED,
        OfficeMembership.Status.REVOKED,
    }:
        raise DomainAPIException("PERMISSION_DENIED", details={"reason": "cannot_suspend_self"})
    before = {
        "role": membership.role.code,
        "branch_id": membership.branch.public_id if membership.branch else None,
        "status": membership.status,
    }
    if "role_code" in data:
        membership.role = _role_for_office(str(data["role_code"]))
    if "branch_id" in data:
        membership.branch = _branch_for_office(context.office, data.get("branch_id"))
    if "status" in data:
        membership.status = str(data["status"])
        membership.revoked_at = timezone.now() if membership.status == OfficeMembership.Status.REVOKED else None
    membership.save()
    if before["role"] != membership.role.code or before["status"] != membership.status:
        from identity.models import UserSession

        UserSession.objects.filter(user=membership.user, revoked_at__isnull=True).update(revoked_at=timezone.now())
    record_audit(
        action="office.staff.update",
        object_type="office_membership",
        object_id=membership.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before=before,
        after={
            "role": membership.role.code,
            "branch_id": membership.branch.public_id if membership.branch else None,
            "status": membership.status,
        },
    )
    return membership


def latest_verification_case(office: Office, *, lock: bool = False) -> VerificationCase:
    queryset = VerificationCase.objects.filter(office=office).order_by("-version")
    if lock:
        queryset = queryset.select_for_update()
    case = queryset.first()
    if case is None:
        case = VerificationCase.objects.create(office=office)
    return case


def _required_document_types() -> set[str]:
    return {
        item.strip()
        for item in settings.OFFICE_VERIFICATION_REQUIRED_DOCUMENT_TYPES.split(",")
        if item.strip()
    }


def _verification_completeness(case: VerificationCase, *, require_verified: bool) -> list[str]:
    missing: list[str] = []
    office = case.office
    if not office.legal_name:
        missing.append("legal_name")
    if not office.trade_name:
        missing.append("trade_name")
    if not office.support_phone:
        missing.append("support_phone")
    required = _required_document_types()
    documents = OfficeDocument.objects.filter(office=office, document_type__in=required)
    by_type: dict[str, OfficeDocument] = {}
    for document in documents.order_by("document_type", "-created_at"):
        by_type.setdefault(document.document_type, document)
    today = timezone.localdate()
    for document_type in required:
        latest_document = by_type.get(document_type)
        if latest_document is None:
            missing.append(f"document:{document_type}")
            continue
        if require_verified and (
            latest_document.status != OfficeDocument.Status.VERIFIED
            or (latest_document.expires_at is not None and latest_document.expires_at < today)
        ):
            missing.append(f"document:{document_type}:not_verified")
    return missing


def office_has_expired_critical_document(office: Office) -> bool:
    today = timezone.localdate()
    return OfficeDocument.objects.filter(office=office, is_critical=True).filter(
        Q(status=OfficeDocument.Status.EXPIRED) | Q(expires_at__lt=today)
    ).exists()


@transaction.atomic
def command_verification(
    *,
    office: Office,
    actor: User,
    request: HttpRequest,
    command: str,
    reason: str | None = None,
    conditions: dict[str, Any] | None = None,
) -> VerificationCase:
    case = latest_verification_case(office, lock=True)
    before = {
        "status": case.status,
        "version": case.version,
        "reviewer_user_id": str(case.reviewer_user_id) if case.reviewer_user_id else None,
    }
    now = timezone.now()

    if command == "submit":
        if case.status != VerificationCase.Status.DRAFT:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        missing = _verification_completeness(case, require_verified=False)
        if missing:
            raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"missing": missing})
        case.status = VerificationCase.Status.SUBMITTED
        case.submitted_at = now
        office.status = Office.Status.SUBMITTED
    elif command == "start_review":
        if case.status != VerificationCase.Status.SUBMITTED:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        case.status = VerificationCase.Status.UNDER_REVIEW
        case.reviewer_user = actor
        office.status = Office.Status.UNDER_REVIEW
    elif command == "request_info":
        if case.status != VerificationCase.Status.UNDER_REVIEW:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if not reason:
            raise DomainAPIException("VERIFICATION_REASON_REQUIRED")
        case.status = VerificationCase.Status.INFO_REQUIRED
        case.decision_reason = reason
    elif command == "resubmit":
        if case.status != VerificationCase.Status.INFO_REQUIRED:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        missing = _verification_completeness(case, require_verified=False)
        if missing:
            raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"missing": missing})
        case = VerificationCase.objects.create(
            office=office,
            status=VerificationCase.Status.SUBMITTED,
            risk_level=case.risk_level,
            submitted_at=now,
            version=case.version + 1,
        )
        office.status = Office.Status.SUBMITTED
    elif command == "external_check":
        if case.status != VerificationCase.Status.UNDER_REVIEW:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        case.status = VerificationCase.Status.EXTERNAL_VERIFICATION
    elif command == "conditional_approve":
        if case.status not in {
            VerificationCase.Status.UNDER_REVIEW,
            VerificationCase.Status.EXTERNAL_VERIFICATION,
        }:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if not conditions:
            raise DomainAPIException("VERIFICATION_CONDITIONS_REQUIRED")
        case.status = VerificationCase.Status.CONDITIONAL
        case.conditions = conditions
        case.approver_user = actor
        case.decided_at = now
        office.status = Office.Status.CONDITIONAL
    elif command == "approve":
        if case.status not in {
            VerificationCase.Status.UNDER_REVIEW,
            VerificationCase.Status.EXTERNAL_VERIFICATION,
            VerificationCase.Status.CONDITIONAL,
        }:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        missing = _verification_completeness(case, require_verified=True)
        if missing:
            raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"missing": missing})
        if (
            case.risk_level == VerificationCase.RiskLevel.ENHANCED
            and case.reviewer_user_id == actor.id
        ):
            raise DomainAPIException("DUAL_APPROVAL_REQUIRED")
        case.status = VerificationCase.Status.APPROVED
        case.approver_user = actor
        case.decided_at = now
        case.decision_reason = reason or case.decision_reason
        office.status = Office.Status.ACTIVE
        office.activated_at = office.activated_at or now
    elif command == "reject":
        if case.status not in {
            VerificationCase.Status.UNDER_REVIEW,
            VerificationCase.Status.EXTERNAL_VERIFICATION,
        }:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if not reason:
            raise DomainAPIException("VERIFICATION_REASON_REQUIRED")
        case.status = VerificationCase.Status.REJECTED
        case.approver_user = actor
        case.decided_at = now
        case.decision_reason = reason
    elif command == "expire":
        if case.status not in {
            VerificationCase.Status.APPROVED,
            VerificationCase.Status.CONDITIONAL,
        }:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if not office_has_expired_critical_document(office):
            raise DomainAPIException("VERIFICATION_NOT_EXPIRED")
        case.status = VerificationCase.Status.EXPIRED
        case.decided_at = now
        office.status = Office.Status.RESTRICTED
    else:
        raise DomainAPIException("VALIDATION_ERROR", details={"field": "command", "reason": "unsupported"})

    case.save()
    office.save()
    OutboxEvent.objects.create(
        aggregate_type="verification_case",
        aggregate_id=case.id,
        event_type="office.verification.status_changed",
        payload={
            "office_id": str(office.id),
            "case_id": str(case.id),
            "status": case.status,
            "command": command,
        },
    )
    record_audit(
        action=f"platform.office_verification.{command}",
        object_type="verification_case",
        object_id=case.id,
        actor_user=actor,
        office_id=office.id,
        request=request,
        before=before,
        after={
            "status": case.status,
            "version": case.version,
            "reviewer_user_id": str(case.reviewer_user_id) if case.reviewer_user_id else None,
            "approver_user_id": str(case.approver_user_id) if case.approver_user_id else None,
        },
        reason_code=reason,
        metadata={"conditions": conditions or {}},
    )
    return case


@transaction.atomic
def register_office_document(
    *, context: OfficeContext, actor: User, request: HttpRequest, data: dict[str, Any]
) -> OfficeDocument:
    case = latest_verification_case(context.office, lock=True)
    try:
        document = OfficeDocument.objects.create(
            office=context.office,
            verification_case=case,
            document_type=str(data["document_type"]).strip(),
            storage_object_key=str(data["storage_object_key"]).strip(),
            sha256=str(data["sha256"]).lower(),
            issued_at=data.get("issued_at"),
            expires_at=data.get("expires_at"),
            is_critical=bool(data.get("is_critical", True)),
        )
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "document_already_registered"}) from exc
    record_audit(
        action="office.verification.document.register",
        object_type="office_document",
        object_id=document.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={
            "document_type": document.document_type,
            "sha256": document.sha256,
            "expires_at": document.expires_at.isoformat() if document.expires_at else None,
        },
    )
    return document


@transaction.atomic
def review_office_document(
    *,
    office: Office,
    document_id: uuid.UUID,
    actor: User,
    request: HttpRequest,
    status: str,
    reason: str | None = None,
) -> OfficeDocument:
    document = OfficeDocument.objects.select_for_update().filter(id=document_id, office=office).first()
    if document is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    before = {
        "status": document.status,
        "reviewed_by_id": str(document.reviewed_by_id) if document.reviewed_by_id else None,
    }
    document.status = status
    document.reviewed_by = actor
    document.reviewed_at = timezone.now()
    document.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    record_audit(
        action="platform.office_document.review",
        object_type="office_document",
        object_id=document.id,
        actor_user=actor,
        office_id=office.id,
        request=request,
        before=before,
        after={"status": document.status, "reviewed_by_id": str(actor.id)},
        reason_code=reason,
    )
    return document


def require_fresh_mfa(request: HttpRequest) -> None:
    """Require evidence that the current server-side session completed MFA recently."""
    from identity.models import UserSession

    session = getattr(request, "auth", None)
    cutoff = timezone.now() - timedelta(seconds=settings.SENSITIVE_MFA_MAX_AGE_SECONDS)
    if not isinstance(session, UserSession) or session.mfa_verified_at is None or session.mfa_verified_at < cutoff:
        raise DomainAPIException("AUTH_MFA_REQUIRED", details={"reason": "fresh_mfa_required"})


@transaction.atomic
def request_payout_account_change(
    *, context: OfficeContext, actor: User, request: HttpRequest, data: dict[str, Any]
) -> OfficePayoutAccount:
    from identity.crypto import encrypt_secret

    require_fresh_mfa(request)
    account_reference = str(data["account_reference"]).strip()
    if len(account_reference) < 4:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "account_reference", "reason": "too_short"}],
        )
    if OfficePayoutAccount.objects.filter(
        office=context.office,
        status__in=[OfficePayoutAccount.Status.PENDING, OfficePayoutAccount.Status.VERIFIED],
    ).exists():
        raise DomainAPIException("CONFLICT", details={"reason": "payout_change_already_pending"})

    account = OfficePayoutAccount.objects.create(
        office=context.office,
        method_type=data["method_type"],
        account_holder_name=str(data["account_holder_name"]).strip(),
        account_reference_ciphertext=encrypt_secret(account_reference),
        account_reference_last4=account_reference[-4:],
        status=OfficePayoutAccount.Status.PENDING,
        created_by=actor,
    )
    OutboxEvent.objects.create(
        aggregate_type="office_payout_account",
        aggregate_id=account.id,
        event_type="office.payout.change_requested",
        payload={
            "office_id": str(context.office.id),
            "account_id": str(account.id),
            "requested_by": str(actor.id),
        },
    )
    record_audit(
        action="office.payout.change_request",
        object_type="office_payout_account",
        object_id=account.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={
            "method_type": account.method_type,
            "account_reference_last4": account.account_reference_last4,
            "status": account.status,
        },
    )
    return account


@transaction.atomic
def approve_payout_account_change(
    *, context: OfficeContext, actor: User, request: HttpRequest, account_id: uuid.UUID
) -> OfficePayoutAccount:
    require_fresh_mfa(request)
    account = (
        OfficePayoutAccount.objects.select_for_update()
        .filter(id=account_id, office=context.office)
        .first()
    )
    if account is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if account.status != OfficePayoutAccount.Status.PENDING:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    if account.created_by_id == actor.id:
        raise DomainAPIException("DUAL_APPROVAL_REQUIRED")

    now = timezone.now()
    account.status = OfficePayoutAccount.Status.VERIFIED
    account.approved_by = actor
    account.verified_at = now
    account.effective_at = now + timedelta(hours=settings.PAYOUT_ACCOUNT_COOLING_HOURS)
    account.save(update_fields=["status", "approved_by", "verified_at", "effective_at"])

    previous = OfficePayoutAccount.objects.filter(
        office=context.office,
        status=OfficePayoutAccount.Status.ACTIVE,
    ).first()
    OutboxEvent.objects.create(
        aggregate_type="office_payout_account",
        aggregate_id=account.id,
        event_type="notification.requested",
        payload={
            "template": "payout_account_change_scheduled",
            "office_id": str(context.office.id),
            "new_account_id": str(account.id),
            "previous_account_id": str(previous.id) if previous else None,
            "previous_account_last4": previous.account_reference_last4 if previous else None,
            "effective_at": account.effective_at.isoformat(),
        },
    )
    record_audit(
        action="office.payout.change_approve",
        object_type="office_payout_account",
        object_id=account.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before={"status": OfficePayoutAccount.Status.PENDING},
        after={
            "status": account.status,
            "approved_by_id": str(actor.id),
            "effective_at": account.effective_at.isoformat(),
        },
    )
    return account


@transaction.atomic
def activate_due_payout_accounts(*, now: datetime | None = None) -> int:
    """Activate approved payout changes after the cooling window; safe for a scheduled job."""
    effective_now = now or timezone.now()
    account_ids = list(
        OfficePayoutAccount.objects.filter(
            status=OfficePayoutAccount.Status.VERIFIED,
            effective_at__isnull=False,
            effective_at__lte=effective_now,
        ).values_list("id", flat=True)
    )
    activated = 0
    for account_id in account_ids:
        account = OfficePayoutAccount.objects.select_for_update().get(id=account_id)
        if (
            account.status != OfficePayoutAccount.Status.VERIFIED
            or account.effective_at is None
            or account.effective_at > effective_now
        ):
            continue
        OfficePayoutAccount.objects.filter(
            office=account.office,
            status=OfficePayoutAccount.Status.ACTIVE,
        ).exclude(id=account.id).update(status=OfficePayoutAccount.Status.REPLACED)
        account.status = OfficePayoutAccount.Status.ACTIVE
        account.save(update_fields=["status"])
        OutboxEvent.objects.create(
            aggregate_type="office_payout_account",
            aggregate_id=account.id,
            event_type="office.payout.change_activated",
            payload={"office_id": str(account.office_id), "account_id": str(account.id)},
        )
        activated += 1
    return activated


def assert_office_assignable_for_new_trip(office: Office) -> None:
    if office.status not in {Office.Status.ACTIVE, Office.Status.CONDITIONAL}:
        raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"reason": "office_not_bookable"})
    if office_has_expired_critical_document(office):
        raise DomainAPIException(
            "VERIFICATION_INCOMPLETE",
            details={"reason": "office_critical_document_expired"},
        )
