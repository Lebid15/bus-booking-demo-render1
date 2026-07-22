from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.models import OutboxEvent
from identity.models import CustomerProfile, User, UserDevice, UserSession
from organizations.models import OfficeMembership
from securityops.models import DataSubjectRequest, LegalHold, RiskAssessment, RiskChallenge, StoredFile
from securityops.scanners import scan_stored_file

_ALLOWED_FILES: dict[str, tuple[set[str], int]] = {
    "office_verification": ({"application/pdf", "image/jpeg", "image/png"}, 10 * 1024 * 1024),
    "identity_document": ({"application/pdf", "image/jpeg", "image/png"}, 10 * 1024 * 1024),
    "manual_transfer_proof": ({"application/pdf", "image/jpeg", "image/png"}, 8 * 1024 * 1024),
    "support_attachment": ({"application/pdf", "image/jpeg", "image/png"}, 8 * 1024 * 1024),
}
_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def _hash(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def _office_id_for_user(user: User) -> uuid.UUID | None:
    office_ids = list(OfficeMembership.objects.for_user(user).values_list("office_id", flat=True)[:2])
    if len(office_ids) > 1:
        raise DomainAPIException("TENANT_ACCESS_DENIED", details={"reason": "multiple_office_contexts"})
    return office_ids[0] if office_ids else None


def _owner_for_user(user: User) -> tuple[str, uuid.UUID]:
    office_id = _office_id_for_user(user)
    if office_id is not None:
        return StoredFile.OwnerScope.OFFICE, office_id
    if user.is_platform_staff:
        return StoredFile.OwnerScope.PLATFORM, user.id
    return StoredFile.OwnerScope.USER, user.id


def _validate_upload(*, purpose: str, filename: str, mime_type: str, size_bytes: int) -> None:
    rule = _ALLOWED_FILES.get(purpose)
    extension = PurePath(filename.lower()).suffix
    if rule is None or mime_type not in rule[0] or extension not in _ALLOWED_EXTENSIONS:
        raise DomainAPIException("FILE_TYPE_NOT_ALLOWED")
    if size_bytes <= 0 or size_bytes > rule[1]:
        raise DomainAPIException(
            "VALIDATION_ERROR", details=[{"field": "size_bytes", "reason": "outside_allowed_range"}]
        )


@transaction.atomic
def create_upload_intent(
    *, user: User, request: HttpRequest, idempotency_key: str, data: dict[str, Any]
) -> dict[str, Any]:
    purpose = str(data["purpose"])
    filename = PurePath(str(data["filename"])).name
    mime_type = str(data["mime_type"]).lower()
    size_bytes = int(data["size_bytes"])
    _validate_upload(purpose=purpose, filename=filename, mime_type=mime_type, size_bytes=size_bytes)
    owner_scope, owner_id = _owner_for_user(user)
    idem, replay = begin_idempotency(
        scope_type="file_upload_intent",
        scope_id=owner_id,
        key=idempotency_key,
        payload=data,
    )
    if replay is not None:
        return replay
    file_id = uuid.uuid4()
    expires_at = timezone.now() + timedelta(minutes=15)
    file = StoredFile.objects.create(
        id=file_id,
        owner_scope=owner_scope,
        owner_id=owner_id,
        purpose=purpose,
        object_key=f"quarantine/{file_id.hex}",
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256=secrets.token_hex(32),
        scan_status=StoredFile.ScanStatus.QUARANTINED,
        retention_until=timezone.now() + timedelta(days=2),
        created_by=user,
    )
    response = {
        "file_id": str(file.id),
        "upload_url": f"{str(getattr(settings, 'PRIVATE_UPLOAD_BASE_URL', 'https://upload.invalid')).rstrip('/')}/{file.id}",
        "expires_at": expires_at,
    }
    complete_idempotency(idem, response)
    record_audit(
        action="file.upload_intent.create",
        object_type="stored_file",
        object_id=file.id,
        actor_user=user,
        office_id=owner_id if owner_scope == StoredFile.OwnerScope.OFFICE else None,
        request=request,
        after={"purpose": purpose, "mime_type": mime_type, "size_bytes": size_bytes, "status": file.scan_status},
    )
    return response


def _owned_file(*, user: User, file_id: uuid.UUID, for_update: bool = False) -> StoredFile:
    owner_scope, owner_id = _owner_for_user(user)
    queryset = StoredFile.objects.select_for_update() if for_update else StoredFile.objects.all()
    file = queryset.filter(id=file_id, owner_scope=owner_scope, owner_id=owner_id, deleted_at__isnull=True).first()
    if file is None:
        # Deliberately return not found rather than tenant metadata or ownership hints.
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return file


def complete_upload(
    *, user: User, request: HttpRequest, file_id: uuid.UUID, idempotency_key: str, sha256: str
) -> dict[str, Any]:
    if len(sha256) != 64 or any(character not in "0123456789abcdefABCDEF" for character in sha256):
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "sha256", "reason": "hex64_required"}])
    owner_scope, owner_id = _owner_for_user(user)
    deferred_error: str | None = None
    response: dict[str, Any] | None = None
    with transaction.atomic():
        file = _owned_file(user=user, file_id=file_id, for_update=True)
        idem, replay = begin_idempotency(
            scope_type="file_upload_complete",
            scope_id=file.id,
            key=idempotency_key,
            payload={"sha256": sha256.lower()},
        )
        if replay is not None:
            return replay
        if file.scan_status == StoredFile.ScanStatus.CLEAN:
            response = {"file_id": str(file.id), "scan_status": file.scan_status}
            complete_idempotency(idem, response)
        else:
            result = scan_stored_file(file, sha256.lower())
            metadata_mismatch = (
                result.sha256.lower() != sha256.lower()
                or result.detected_mime != file.mime_type
                or result.size_bytes != file.size_bytes
            )
            if metadata_mismatch:
                file.scan_status = StoredFile.ScanStatus.REJECTED
                file.save(update_fields=["scan_status"])
                record_audit(
                    action="file.scan.reject",
                    object_type="stored_file",
                    object_id=file.id,
                    actor_user=user,
                    office_id=owner_id if owner_scope == StoredFile.OwnerScope.OFFICE else None,
                    request=request,
                    reason_code="FILE_METADATA_MISMATCH",
                    after={"scan_status": file.scan_status, "scanner": result.engine},
                )
                deferred_error = "FILE_TYPE_NOT_ALLOWED"
            elif not result.clean:
                file.sha256 = sha256.lower()
                file.scan_status = StoredFile.ScanStatus.REJECTED
                file.retention_until = timezone.now() + timedelta(days=7)
                file.save(update_fields=["sha256", "scan_status", "retention_until"])
                record_audit(
                    action="file.scan.reject",
                    object_type="stored_file",
                    object_id=file.id,
                    actor_user=user,
                    office_id=owner_id if owner_scope == StoredFile.OwnerScope.OFFICE else None,
                    request=request,
                    reason_code="FILE_MALWARE_DETECTED",
                    after={"scan_status": file.scan_status, "scanner": result.engine, "malware": "[REDACTED]"},
                )
                deferred_error = "FILE_MALWARE_DETECTED"
            else:
                duplicate = StoredFile.objects.filter(
                    owner_scope=file.owner_scope,
                    owner_id=file.owner_id,
                    purpose=file.purpose,
                    sha256=sha256.lower(),
                ).exclude(id=file.id).exists()
                if duplicate:
                    raise DomainAPIException("CONFLICT", details={"reason": "duplicate_file_hash"})
                file.sha256 = sha256.lower()
                file.scan_status = StoredFile.ScanStatus.CLEAN
                file.object_key = f"private/{file.purpose}/{file.id.hex}"
                file.retention_until = timezone.now() + timedelta(
                    days=int(getattr(settings, "FILE_RETENTION_DAYS", 365))
                )
                file.save(update_fields=["sha256", "scan_status", "object_key", "retention_until"])
                response = {"file_id": str(file.id), "scan_status": file.scan_status}
                complete_idempotency(idem, response)
                record_audit(
                    action="file.scan.clean",
                    object_type="stored_file",
                    object_id=file.id,
                    actor_user=user,
                    office_id=owner_id if owner_scope == StoredFile.OwnerScope.OFFICE else None,
                    request=request,
                    after={"scan_status": file.scan_status, "scanner": result.engine},
                )
    if deferred_error is not None:
        raise DomainAPIException(deferred_error)
    if response is None:
        raise DomainAPIException("CONFLICT", details={"reason": "upload_completion_missing_result"})
    return response


def active_legal_hold(*, subject_type: str, subject_id: uuid.UUID) -> LegalHold | None:
    return LegalHold.objects.filter(subject_type=subject_type, subject_id=subject_id, active=True).first()


def _require_recent_mfa(request: HttpRequest) -> None:
    session = getattr(request, "auth", None)
    cutoff = timezone.now() - timedelta(seconds=int(settings.SENSITIVE_MFA_MAX_AGE_SECONDS))
    if not isinstance(session, UserSession) or session.mfa_verified_at is None or session.mfa_verified_at < cutoff:
        raise DomainAPIException("AUTH_MFA_REQUIRED")


@transaction.atomic
def request_data_export(
    *, user: User, request: HttpRequest, idempotency_key: str
) -> dict[str, Any]:
    if active_legal_hold(subject_type=LegalHold.SubjectType.USER, subject_id=user.id):
        record_audit(
            action="privacy.export.blocked",
            object_type="user",
            object_id=user.id,
            actor_user=user,
            request=request,
            reason_code="LEGAL_HOLD_ACTIVE",
        )
        raise DomainAPIException("LEGAL_HOLD_ACTIVE")
    idem, replay = begin_idempotency(
        scope_type="privacy_export", scope_id=user.id, key=idempotency_key, payload={"request_type": "export"}
    )
    if replay is not None:
        return replay
    dsr = DataSubjectRequest.objects.create(
        user=user,
        request_type=DataSubjectRequest.RequestType.EXPORT,
        status=DataSubjectRequest.Status.SUBMITTED,
        due_at=timezone.now() + timedelta(days=30),
    )
    response = {"request_id": str(dsr.id), "status": dsr.status}
    complete_idempotency(idem, response)
    OutboxEvent.objects.create(
        aggregate_type="data_subject_request",
        aggregate_id=dsr.id,
        event_type="privacy.data_export.requested",
        payload={"request_id": str(dsr.id), "user_id": str(user.id)},
    )
    record_audit(
        action="privacy.export.request",
        object_type="data_subject_request",
        object_id=dsr.id,
        actor_user=user,
        request=request,
        after={"status": dsr.status, "request_type": dsr.request_type},
    )
    return response


def _anonymize_user(*, user: User, request: HttpRequest | None, dsr: DataSubjectRequest) -> None:
    now = timezone.now()
    deleted_marker = user.id.hex[:12]
    Booking.objects.filter(customer_user=user).update(
        contact_name="مستخدم محذوف",
        contact_email=None,
        contact_phone=f"deleted-{deleted_marker}",
    )
    CustomerProfile.objects.filter(user=user).update(
        date_of_birth=None,
        gender=None,
        nationality_code=None,
        marketing_consent=False,
        deleted_at=now,
    )
    UserSession.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now)
    UserDevice.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now)
    user.email = f"deleted+{user.id.hex}@privacy.invalid"
    user.phone_e164 = None
    user.full_name = "مستخدم محذوف"
    user.status = User.Status.DELETED
    user.set_unusable_password()
    user.save(update_fields=["email", "phone_e164", "full_name", "status", "password", "updated_at"])
    dsr.status = DataSubjectRequest.Status.FULFILLED
    dsr.completed_at = now
    dsr.decision_reason = (
        "account_disabled_and_nonessential_identity_anonymized; "
        "mandatory booking and finance records retained"
    )
    dsr.save(update_fields=["status", "completed_at", "decision_reason"])
    OutboxEvent.objects.create(
        aggregate_type="data_subject_request",
        aggregate_id=dsr.id,
        event_type="privacy.account_deletion.fulfilled",
        payload={"request_id": str(dsr.id), "user_id": str(user.id)},
    )
    record_audit(
        action="privacy.account_delete.fulfilled",
        object_type="data_subject_request",
        object_id=dsr.id,
        actor_user=user,
        request=request,
        after={
            "user_status": User.Status.DELETED,
            "identity_fields": "anonymized",
            "mandatory_records": "retained",
        },
    )


@transaction.atomic
def request_account_deletion(
    *, user: User, request: HttpRequest, idempotency_key: str, confirmation: str
) -> dict[str, Any]:
    _require_recent_mfa(request)
    if confirmation.strip().upper() != "DELETE":
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "confirmation", "reason": "DELETE_required"}])
    if active_legal_hold(subject_type=LegalHold.SubjectType.USER, subject_id=user.id):
        record_audit(
            action="privacy.account_delete.blocked",
            object_type="user",
            object_id=user.id,
            actor_user=user,
            request=request,
            reason_code="LEGAL_HOLD_ACTIVE",
        )
        raise DomainAPIException("LEGAL_HOLD_ACTIVE")
    idem, replay = begin_idempotency(
        scope_type="privacy_delete", scope_id=user.id, key=idempotency_key, payload={"confirmation": "DELETE"}
    )
    if replay is not None:
        return replay
    dsr = DataSubjectRequest.objects.create(
        user=user,
        request_type=DataSubjectRequest.RequestType.DELETE,
        status=DataSubjectRequest.Status.IN_PROGRESS,
        due_at=timezone.now() + timedelta(days=30),
    )
    _anonymize_user(user=user, request=request, dsr=dsr)
    response = {"request_id": str(dsr.id)}
    complete_idempotency(idem, response)
    return response


@transaction.atomic
def process_retention_requests(*, limit: int = 100) -> dict[str, int]:
    requests = list(
        DataSubjectRequest.objects.select_for_update(of=("self",))
        .select_related("user")
        .filter(request_type=DataSubjectRequest.RequestType.DELETE)
        .filter(status__in=[DataSubjectRequest.Status.SUBMITTED, DataSubjectRequest.Status.IN_PROGRESS])
        .order_by("submitted_at")[:limit]
    )
    processed = 0
    skipped = 0
    for dsr in requests:
        user = dsr.user
        if user is None:
            dsr.status = DataSubjectRequest.Status.REJECTED
            dsr.decision_reason = "user_missing"
            dsr.completed_at = timezone.now()
            dsr.save(update_fields=["status", "decision_reason", "completed_at"])
            continue
        hold = active_legal_hold(subject_type=LegalHold.SubjectType.USER, subject_id=user.id)
        if hold is not None:
            skipped += 1
            dsr.status = DataSubjectRequest.Status.SUBMITTED
            dsr.decision_reason = f"LEGAL_HOLD_ACTIVE:{hold.id}"
            dsr.save(update_fields=["status", "decision_reason"])
            record_audit(
                action="privacy.retention.skip",
                object_type="data_subject_request",
                object_id=dsr.id,
                actor_type="system",
                reason_code="LEGAL_HOLD_ACTIVE",
                metadata={"hold_id": str(hold.id), "subject_type": hold.subject_type},
            )
            continue
        _anonymize_user(user=user, request=None, dsr=dsr)
        processed += 1
    return {"processed": processed, "skipped_legal_hold": skipped}


@transaction.atomic
def place_legal_hold(
    *, actor: User, request: HttpRequest, idempotency_key: str, data: dict[str, Any]
) -> dict[str, Any]:
    subject_type = str(data["subject_type"])
    subject_id = uuid.UUID(str(data["subject_id"]))
    idem, replay = begin_idempotency(
        scope_type="legal_hold_place",
        scope_id=subject_id,
        key=idempotency_key,
        payload=data,
    )
    if replay is not None:
        return replay
    try:
        hold = LegalHold.objects.create(
            subject_type=subject_type,
            subject_id=subject_id,
            reason=str(data["reason"]).strip(),
            placed_by=actor,
        )
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "active_legal_hold_exists"}) from exc
    response = serialize_legal_hold(hold)
    complete_idempotency(idem, response)
    record_audit(
        action="privacy.legal_hold.place",
        object_type="legal_hold",
        object_id=hold.id,
        actor_user=actor,
        request=request,
        after=response,
        reason_code="legal_hold",
    )
    return response


@transaction.atomic
def release_legal_hold(
    *, actor: User, request: HttpRequest, hold_id: uuid.UUID, idempotency_key: str, reason: str
) -> dict[str, Any]:
    hold = LegalHold.objects.select_for_update().filter(id=hold_id, active=True).first()
    if hold is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    idem, replay = begin_idempotency(
        scope_type="legal_hold_release",
        scope_id=hold.id,
        key=idempotency_key,
        payload={"reason": reason},
    )
    if replay is not None:
        return replay
    hold.active = False
    hold.released_by = actor
    hold.released_at = timezone.now()
    hold.save(update_fields=["active", "released_by", "released_at"])
    response = serialize_legal_hold(hold)
    complete_idempotency(idem, response)
    record_audit(
        action="privacy.legal_hold.release",
        object_type="legal_hold",
        object_id=hold.id,
        actor_user=actor,
        request=request,
        before={"active": True},
        after={"active": False},
        reason_code=reason,
    )
    return response


def serialize_legal_hold(hold: LegalHold) -> dict[str, Any]:
    return {
        "id": str(hold.id),
        "subject_type": hold.subject_type,
        "subject_id": str(hold.subject_id),
        "reason": hold.reason,
        "active": hold.active,
        "placed_at": hold.placed_at,
        "released_at": hold.released_at,
    }


def _risk_score(*, payload: dict[str, Any], request: HttpRequest) -> tuple[Decimal, dict[str, Any]]:
    score = Decimal("5")
    signals: dict[str, Any] = {}
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if len(user_agent.strip()) < 8:
        score += Decimal("20")
        signals["missing_user_agent"] = True
    raw_user = getattr(request, "user", None)
    if not isinstance(raw_user, User):
        score += Decimal("15")
        signals["guest_checkout"] = True
    passenger_count = len(payload.get("passengers", [])) if isinstance(payload.get("passengers"), list) else 0
    if passenger_count >= 6:
        score += Decimal("20")
        signals["large_party"] = passenger_count
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded.count(",") >= 2:
        score += Decimal("15")
        signals["proxy_chain"] = True
    client_reference = str(payload.get("client_reference") or "")
    if client_reference.lower().startswith("risk-") and str(settings.APP_ENV) != "production":
        # Internal QA/provider convention only; it never lowers risk and is ignored outside non-production.
        try:
            score = max(score, Decimal(client_reference.split("-", 1)[1]))
            signals["qa_floor"] = str(score)
        except (ArithmeticError, ValueError):
            pass
    return min(score, Decimal("100")), signals


def _challenge_code_hash(challenge_id: uuid.UUID, code: str) -> bytes:
    key = str(getattr(settings, "RISK_STEP_UP_SIGNING_KEY", settings.SECRET_KEY)).encode()
    return hmac.new(key, f"{challenge_id}:{code}".encode(), hashlib.sha256).digest()


def _step_up_token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _consume_step_up_token(*, subject_id: uuid.UUID, token: str) -> bool:
    now = timezone.now()
    challenge = (
        RiskChallenge.objects.select_for_update()
        .select_related("assessment")
        .filter(
            token_hash=_step_up_token_hash(token),
            verified_at__isnull=False,
            consumed_at__isnull=True,
            expires_at__gt=now,
            assessment__subject_type=RiskAssessment.SubjectType.BOOKING,
            assessment__subject_id=subject_id,
        )
        .first()
    )
    if challenge is None:
        return False
    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at"])
    return True


def enforce_public_booking_risk(
    *, subject_id: uuid.UUID, payload: dict[str, Any], request: HttpRequest
) -> RiskAssessment:
    deferred_error: DomainAPIException | None = None
    with transaction.atomic():
        token = request.headers.get("X-Risk-Step-Up-Token", "").strip()
        if token and _consume_step_up_token(subject_id=subject_id, token=token):
            assessment = RiskAssessment.objects.create(
                subject_type=RiskAssessment.SubjectType.BOOKING,
                subject_id=subject_id,
                score=Decimal("0"),
                decision=RiskAssessment.Decision.ALLOW,
                model_version="rules-v1",
                signals={"step_up_verified": True},
                review_status="verified",
            )
            request.__dict__["risk_assessment_id"] = assessment.id
            record_audit(
                action="risk.booking.allow_after_step_up",
                object_type="risk_assessment",
                object_id=assessment.id,
                actor_type="guest",
                request=request,
                after={"decision": assessment.decision, "score": str(assessment.score)},
            )
            return assessment

        score, signals = _risk_score(payload=payload, request=request)
        step_threshold = Decimal(str(getattr(settings, "RISK_STEP_UP_THRESHOLD", "50")))
        review_threshold = Decimal(str(getattr(settings, "RISK_MANUAL_REVIEW_THRESHOLD", "70")))
        block_threshold = Decimal(str(getattr(settings, "RISK_BLOCK_THRESHOLD", "90")))
        if score >= block_threshold:
            decision = RiskAssessment.Decision.BLOCK
        elif score >= review_threshold:
            decision = RiskAssessment.Decision.MANUAL_REVIEW
        elif score >= step_threshold:
            decision = RiskAssessment.Decision.STEP_UP
        else:
            decision = RiskAssessment.Decision.ALLOW
        assessment = RiskAssessment.objects.create(
            subject_type=RiskAssessment.SubjectType.BOOKING,
            subject_id=subject_id,
            score=score,
            decision=decision,
            model_version="rules-v1",
            signals=signals,
            review_status="pending" if decision != RiskAssessment.Decision.ALLOW else "not_required",
        )
        request.__dict__["risk_assessment_id"] = assessment.id
        record_audit(
            action=f"risk.booking.{decision}",
            object_type="risk_assessment",
            object_id=assessment.id,
            actor_type="guest",
            request=request,
            after={"decision": decision, "score": str(score), "signals": signals},
        )
        if decision == RiskAssessment.Decision.STEP_UP:
            challenge_id = uuid.uuid4()
            code = str(getattr(settings, "RISK_STEP_UP_CODE", "123456"))
            RiskChallenge.objects.create(
                id=challenge_id,
                assessment=assessment,
                code_hash=_challenge_code_hash(challenge_id, code),
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            deferred_error = DomainAPIException(
                "AUTH_MFA_REQUIRED",
                details={"challenge_id": str(challenge_id), "method": "otp", "reason": "risk_step_up"},
            )
        elif decision == RiskAssessment.Decision.MANUAL_REVIEW:
            deferred_error = DomainAPIException(
                "RISK_MANUAL_REVIEW_REQUIRED",
                details={"risk_assessment_id": str(assessment.id)},
            )
        elif decision == RiskAssessment.Decision.BLOCK:
            deferred_error = DomainAPIException("RISK_BLOCKED")
    if deferred_error is not None:
        raise deferred_error
    return assessment


def verify_risk_challenge(*, challenge_id: uuid.UUID, code: str, request: HttpRequest) -> dict[str, Any]:
    deferred_error: DomainAPIException | None = None
    response: dict[str, Any] | None = None
    with transaction.atomic():
        challenge = (
            RiskChallenge.objects.select_for_update().select_related("assessment").filter(id=challenge_id).first()
        )
        now = timezone.now()
        if challenge is None or challenge.expires_at <= now or challenge.consumed_at is not None:
            deferred_error = DomainAPIException("AUTH_MFA_INVALID")
        else:
            challenge.attempts += 1
            valid = hmac.compare_digest(bytes(challenge.code_hash), _challenge_code_hash(challenge.id, code))
            if challenge.attempts > 5 or not valid:
                challenge.save(update_fields=["attempts"])
                record_audit(
                    action="risk.step_up.failed",
                    object_type="risk_challenge",
                    object_id=challenge.id,
                    actor_type="guest",
                    request=request,
                    reason_code="AUTH_MFA_INVALID",
                    after={"attempts": challenge.attempts, "code": "[REDACTED]"},
                )
                deferred_error = DomainAPIException("AUTH_MFA_INVALID")
            else:
                token = secrets.token_urlsafe(32)
                challenge.token_hash = _step_up_token_hash(token)
                challenge.verified_at = now
                challenge.save(update_fields=["attempts", "token_hash", "verified_at"])
                record_audit(
                    action="risk.step_up.verified",
                    object_type="risk_challenge",
                    object_id=challenge.id,
                    actor_type="guest",
                    request=request,
                    after={"assessment_id": str(challenge.assessment_id), "token": "[REDACTED]"},  # nosec B105
                )
                response = {"step_up_token": token, "expires_at": challenge.expires_at}
    if deferred_error is not None:
        raise deferred_error
    if response is None:
        raise DomainAPIException("AUTH_MFA_INVALID")
    return response


def list_risk_assessments(*, decision: str | None = None, subject_type: str | None = None) -> list[dict[str, Any]]:
    queryset = RiskAssessment.objects.all().order_by("-created_at")
    if decision:
        queryset = queryset.filter(decision=decision)
    if subject_type:
        queryset = queryset.filter(subject_type=subject_type)
    return [
        {
            "id": str(item.id),
            "subject_type": item.subject_type,
            "subject_id": str(item.subject_id),
            "score": str(item.score),
            "decision": item.decision,
            "model_version": item.model_version,
            "signals": item.signals,
            "review_status": item.review_status,
            "created_at": item.created_at,
        }
        for item in queryset[:200]
    ]
