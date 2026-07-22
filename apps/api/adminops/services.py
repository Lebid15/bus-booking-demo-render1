from __future__ import annotations

from typing import Any

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from adminops.models import OfficeStatusAction, PlatformActionApproval
from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.models import OutboxEvent
from identity.models import User
from organizations.models import Office
from organizations.services import require_fresh_mfa

CRITICAL_OFFICE_STATUSES = {Office.Status.SUSPENDED, Office.Status.TERMINATED}


def serialize_approval(approval: PlatformActionApproval) -> dict[str, Any]:
    return {
        "id": approval.public_id,
        "action_type": approval.action_type,
        "target_type": approval.target_type,
        "target_id": str(approval.target_id),
        "payload": approval.payload,
        "risk_level": approval.risk_level,
        "status": approval.status,
        "reason": approval.reason,
        "requested_by": approval.requested_by.public_id,
        "approved_by": approval.approved_by.public_id if approval.approved_by is not None else None,
        "requested_at": approval.requested_at,
        "approved_at": approval.approved_at,
        "executed_at": approval.executed_at,
    }


def _apply_office_status(
    *, office: Office, new_status: str, reason: str, actor: User, request: HttpRequest | None
) -> OfficeStatusAction:
    previous_status = office.status
    office.status = new_status
    office.save(update_fields=["status", "updated_at"])
    action = OfficeStatusAction.objects.create(
        office=office,
        previous_status=previous_status,
        new_status=new_status,
        reason=reason,
        actor=actor,
    )
    OutboxEvent.objects.create(
        aggregate_type="office",
        aggregate_id=office.id,
        event_type="office.status.changed",
        payload={
            "office_id": office.public_id,
            "previous_status": previous_status,
            "new_status": new_status,
            "existing_bookings_preserved": True,
        },
    )
    record_audit(
        action="platform.office.status.changed",
        object_type="office",
        object_id=office.id,
        actor_user=actor,
        office_id=office.id,
        request=request,
        before={"status": previous_status},
        after={"status": new_status, "existing_bookings_preserved": True},
        reason_code=reason,
    )
    return action


@transaction.atomic
def request_office_status_change(
    *,
    office: Office,
    new_status: str,
    reason: str,
    actor: User,
    request: HttpRequest,
    idempotency_key: str,
) -> dict[str, Any]:
    locked = Office.objects.select_for_update().get(id=office.id)
    payload = {"status": new_status, "reason": reason}
    idem, replay = begin_idempotency(
        scope_type="platform_office_status",
        scope_id=locked.id,
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return replay

    if new_status in CRITICAL_OFFICE_STATUSES:
        require_fresh_mfa(request)
        approval = PlatformActionApproval.objects.create(
            action_type="office.status.change",
            target_type="office",
            target_id=locked.id,
            payload={"new_status": new_status},
            risk_level="critical",
            reason=reason,
            requested_by=actor,
        )
        response = {
            "id": locked.public_id,
            "status": locked.status,
            "requires_approval": True,
            "approval": serialize_approval(approval),
        }
        record_audit(
            action="platform.office.status.approval_requested",
            object_type="office",
            object_id=locked.id,
            actor_user=actor,
            office_id=locked.id,
            request=request,
            before={"status": locked.status},
            after={"requested_status": new_status, "approval_id": approval.public_id},
            reason_code=reason,
        )
    else:
        action = _apply_office_status(
            office=locked,
            new_status=new_status,
            reason=reason,
            actor=actor,
            request=request,
        )
        response = {
            "id": locked.public_id,
            "status": locked.status,
            "action_id": str(action.id),
            "requires_approval": False,
        }
    complete_idempotency(idem, response)
    return response


@transaction.atomic
def command_platform_approval(
    *,
    approval: PlatformActionApproval,
    command: str,
    actor: User,
    request: HttpRequest,
    idempotency_key: str,
    reason: str,
) -> PlatformActionApproval:
    locked = PlatformActionApproval.objects.select_for_update().select_related("requested_by").get(id=approval.id)
    payload = {"command": command, "reason": reason}
    idem, replay = begin_idempotency(
        scope_type="platform_action_approval",
        scope_id=locked.id,
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return PlatformActionApproval.objects.get(id=replay["approval_id"])
    if locked.status != PlatformActionApproval.Status.PENDING:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    if locked.requested_by_id == actor.id:
        raise DomainAPIException("DUAL_APPROVAL_REQUIRED")
    require_fresh_mfa(request)
    now = timezone.now()
    if command == "reject":
        locked.status = PlatformActionApproval.Status.REJECTED
        locked.approved_by = actor
        locked.approved_at = now
        locked.save(update_fields=["status", "approved_by", "approved_at"])
    elif command == "approve":
        locked.status = PlatformActionApproval.Status.APPROVED
        locked.approved_by = actor
        locked.approved_at = now
        locked.save(update_fields=["status", "approved_by", "approved_at"])
        if locked.action_type == "office.status.change" and locked.target_type == "office":
            office = Office.objects.select_for_update().get(id=locked.target_id)
            _apply_office_status(
                office=office,
                new_status=str(locked.payload["new_status"]),
                reason=locked.reason,
                actor=actor,
                request=request,
            )
        else:
            raise DomainAPIException("VALIDATION_ERROR", details={"reason": "unsupported_approval_action"})
        locked.status = PlatformActionApproval.Status.EXECUTED
        locked.executed_at = now
        locked.save(update_fields=["status", "executed_at"])
    else:
        raise DomainAPIException("VALIDATION_ERROR")
    record_audit(
        action=f"platform.approval.{command}",
        object_type="platform_action_approval",
        object_id=locked.id,
        actor_user=actor,
        request=request,
        before={"status": PlatformActionApproval.Status.PENDING},
        after={"status": locked.status, "executed_at": locked.executed_at.isoformat() if locked.executed_at else None},
        reason_code=reason,
        metadata={"requested_by": str(locked.requested_by_id), "approved_by": str(actor.id)},
    )
    complete_idempotency(idem, {"approval_id": str(locked.id)})
    return locked
