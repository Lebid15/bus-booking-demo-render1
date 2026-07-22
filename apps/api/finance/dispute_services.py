from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.models import OutboxEvent
from finance.models import (
    FinancialDispute,
    FinancialDisputeAppeal,
    FinancialDisputeDecision,
    LedgerAccount,
    LedgerEntry,
    LedgerPosting,
)
from finance.services import PostingSpec, money, post_ledger_entry, reverse_ledger_entry
from identity.models import User
from organizations.services import OfficeContext

APPEAL_WINDOW_DAYS = 7


def serialize_dispute(dispute: FinancialDispute) -> dict[str, Any]:
    initial = dispute.decisions.filter(stage=FinancialDisputeDecision.Stage.INITIAL).first()
    appeal_decision = dispute.decisions.filter(stage=FinancialDisputeDecision.Stage.APPEAL).first()
    appeal = getattr(dispute, "appeal", None)
    return {
        "id": str(dispute.id),
        "booking_id": dispute.booking.public_id,
        "office_id": dispute.booking.office.public_id,
        "status": dispute.status,
        "category": dispute.category,
        "disputed_amount": str(dispute.disputed_amount) if dispute.disputed_amount is not None else None,
        "currency": dispute.currency,
        "opened_by_type": dispute.opened_by_type,
        "decision_code": dispute.decision_code,
        "decision_summary": dispute.decision_summary,
        "appeal_deadline_at": dispute.appeal_deadline_at,
        "appealed_at": dispute.appealed_at,
        "initial_decision": serialize_decision(initial) if initial else None,
        "appeal": {
            "filed_by_type": appeal.filed_by_type,
            "reason": appeal.reason,
            "evidence": appeal.evidence,
            "filed_at": appeal.filed_at,
            "decided_at": appeal.decided_at,
        }
        if appeal
        else None,
        "appeal_decision": serialize_decision(appeal_decision) if appeal_decision else None,
        "opened_at": dispute.opened_at,
        "decided_at": dispute.decided_at,
        "closed_at": dispute.closed_at,
    }


def serialize_decision(decision: FinancialDisputeDecision) -> dict[str, Any]:
    return {
        "id": str(decision.id),
        "stage": decision.stage,
        "decision_code": decision.decision_code,
        "reasoning": decision.reasoning,
        "financial_effect": {
            "type": decision.financial_effect_type,
            "amount": str(decision.financial_amount),
            "currency": decision.currency,
            "ledger_entry_id": str(decision.ledger_entry_id) if decision.ledger_entry_id else None,
        },
        "appeal_allowed_until": decision.appeal_allowed_until,
        "is_final": decision.is_final,
        "decided_by": decision.decided_by.public_id,
        "created_at": decision.created_at,
    }


def _effect_postings(effect_type: str, amount: Decimal) -> list[PostingSpec]:
    if effect_type == FinancialDisputeDecision.FinancialEffectType.OFFICE_CREDIT:
        return [
            PostingSpec(
                "DISPUTE_ADJUSTMENT_EXPENSE", LedgerAccount.AccountType.EXPENSE, LedgerPosting.Direction.DEBIT, amount
            ),
            PostingSpec(
                "OFFICE_PAYABLE",
                LedgerAccount.AccountType.LIABILITY,
                LedgerPosting.Direction.CREDIT,
                amount,
                office_scoped=True,
            ),
        ]
    if effect_type == FinancialDisputeDecision.FinancialEffectType.OFFICE_DEBIT:
        return [
            PostingSpec(
                "OFFICE_RECEIVABLE",
                LedgerAccount.AccountType.ASSET,
                LedgerPosting.Direction.DEBIT,
                amount,
                office_scoped=True,
            ),
            PostingSpec("DISPUTE_RECOVERY", LedgerAccount.AccountType.REVENUE, LedgerPosting.Direction.CREDIT, amount),
        ]
    if effect_type == FinancialDisputeDecision.FinancialEffectType.CUSTOMER_COMPENSATION:
        return [
            PostingSpec(
                "DISPUTE_ADJUSTMENT_EXPENSE", LedgerAccount.AccountType.EXPENSE, LedgerPosting.Direction.DEBIT, amount
            ),
            PostingSpec(
                "CUSTOMER_REFUND_PAYABLE", LedgerAccount.AccountType.LIABILITY, LedgerPosting.Direction.CREDIT, amount
            ),
        ]
    return []


def _post_effect(
    *, dispute: FinancialDispute, decision_id: uuid.UUID, effect_type: str, amount: Decimal
) -> LedgerEntry | None:
    if effect_type == FinancialDisputeDecision.FinancialEffectType.NONE or amount == 0:
        return None
    return post_ledger_entry(
        event_type="DISPUTE_DECISION",
        event_id=decision_id,
        currency=dispute.currency,
        occurred_at=timezone.now(),
        postings=_effect_postings(effect_type, amount),
        description=f"Financial effect for dispute {dispute.id}",
        office=dispute.booking.office,
        booking=dispute.booking,
    )


def list_platform_disputes(*, status_filter: str | None = None, office_id: str | None = None) -> list[dict[str, Any]]:
    qs = FinancialDispute.objects.select_related("booking", "booking__office").prefetch_related("decisions__decided_by")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if office_id:
        qs = qs.filter(booking__office__public_id=office_id)
    return [serialize_dispute(item) for item in qs.order_by("-opened_at")]


def list_office_disputes(*, context: OfficeContext) -> list[dict[str, Any]]:
    qs = (
        FinancialDispute.objects.filter(booking__office=context.office)
        .select_related("booking", "booking__office")
        .prefetch_related("decisions__decided_by")
    )
    return [serialize_dispute(item) for item in qs.order_by("-opened_at")]


@transaction.atomic
def command_dispute(
    *,
    dispute: FinancialDispute,
    command: str,
    data: dict[str, Any],
    actor: User,
    request: HttpRequest,
    idempotency_key: str,
    platform_permissions: frozenset[str],
) -> FinancialDispute:
    locked = (
        FinancialDispute.objects.select_for_update().select_related("booking", "booking__office").get(id=dispute.id)
    )
    idem, replay = begin_idempotency(
        scope_type="financial_dispute_command",
        scope_id=locked.id,
        key=idempotency_key,
        payload={"command": command, **data},
    )
    if replay is not None:
        return FinancialDispute.objects.get(id=replay["dispute_id"])
    before = {"status": locked.status, "decision_code": locked.decision_code}
    now = timezone.now()
    if command == "assign_office":
        if locked.status != FinancialDispute.Status.OPEN:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if locked.booking.office_id is None:
            raise DomainAPIException("DISPUTE_OFFICE_NOT_RESPONSIBLE")
        locked.status = FinancialDispute.Status.AWAITING_OFFICE
    elif command == "decide":
        if locked.status not in {FinancialDispute.Status.OPEN, FinancialDispute.Status.UNDER_REVIEW}:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        code = str(data.get("decision_code") or "").strip()
        reasoning = str(data.get("reasoning") or "").strip()
        effect = data.get("financial_effect")
        if not code or len(reasoning) < 10 or not isinstance(effect, dict) or "type" not in effect:
            raise DomainAPIException("DISPUTE_DECISION_INCOMPLETE")
        effect_type = str(effect.get("type"))
        if effect_type not in FinancialDisputeDecision.FinancialEffectType.values:
            raise DomainAPIException("DISPUTE_DECISION_INCOMPLETE")
        amount = money(effect.get("amount", "0"))
        if amount < 0 or (effect_type != FinancialDisputeDecision.FinancialEffectType.NONE and amount <= 0):
            raise DomainAPIException("DISPUTE_DECISION_INCOMPLETE")
        if (
            effect_type != FinancialDisputeDecision.FinancialEffectType.NONE
            and "platform.dispute.finance" not in platform_permissions
        ):
            raise DomainAPIException("PERMISSION_DENIED")
        appeal_deadline = now + timedelta(days=APPEAL_WINDOW_DAYS)
        decision = FinancialDisputeDecision.objects.create(
            dispute=locked,
            stage=FinancialDisputeDecision.Stage.INITIAL,
            decision_code=code,
            reasoning=reasoning,
            financial_effect_type=effect_type,
            financial_amount=amount,
            currency=locked.currency,
            appeal_allowed_until=appeal_deadline,
            is_final=False,
            decided_by=actor,
        )
        decision.ledger_entry = _post_effect(
            dispute=locked, decision_id=decision.id, effect_type=effect_type, amount=amount
        )
        decision.save(update_fields=["ledger_entry"])
        locked.status = FinancialDispute.Status.DECIDED
        locked.decision_code = code
        locked.decision_summary = reasoning
        locked.decided_at = now
        locked.appeal_deadline_at = appeal_deadline
        OutboxEvent.objects.create(
            aggregate_type="financial_dispute",
            aggregate_id=locked.id,
            event_type="dispute.decided",
            payload={
                "dispute_id": str(locked.id),
                "appeal_allowed_until": appeal_deadline.isoformat(),
                "financial_effect": {
                    "type": effect_type,
                    "amount": str(amount),
                    "currency": locked.currency,
                },
            },
        )
    elif command == "decide_appeal":
        if locked.status != FinancialDispute.Status.APPEALED:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        initial = locked.decisions.select_related("ledger_entry", "decided_by").get(
            stage=FinancialDisputeDecision.Stage.INITIAL
        )
        if initial.decided_by_id == actor.id:
            raise DomainAPIException("DUAL_APPROVAL_REQUIRED")
        code = str(data.get("decision_code") or "").strip()
        reasoning = str(data.get("reasoning") or "").strip()
        effect = data.get("financial_effect")
        if not code or len(reasoning) < 10 or not isinstance(effect, dict) or "type" not in effect:
            raise DomainAPIException("DISPUTE_DECISION_INCOMPLETE")
        effect_type = str(effect.get("type"))
        if effect_type not in FinancialDisputeDecision.FinancialEffectType.values:
            raise DomainAPIException("DISPUTE_DECISION_INCOMPLETE")
        amount = money(effect.get("amount", "0"))
        if amount < 0 or (effect_type != FinancialDisputeDecision.FinancialEffectType.NONE and amount <= 0):
            raise DomainAPIException("DISPUTE_DECISION_INCOMPLETE")
        if (
            effect_type != FinancialDisputeDecision.FinancialEffectType.NONE
            and "platform.dispute.finance" not in platform_permissions
        ):
            raise DomainAPIException("PERMISSION_DENIED")
        if initial.ledger_entry_id:
            reverse_ledger_entry(
                original=cast(LedgerEntry, initial.ledger_entry),
                event_id=uuid.uuid4(),
                description=f"Appeal reversal for dispute {locked.id}",
                actor=actor,
                request=request,
            )
        final = FinancialDisputeDecision.objects.create(
            dispute=locked,
            stage=FinancialDisputeDecision.Stage.APPEAL,
            decision_code=code,
            reasoning=reasoning,
            financial_effect_type=effect_type,
            financial_amount=amount,
            currency=locked.currency,
            is_final=True,
            decided_by=actor,
        )
        final.ledger_entry = _post_effect(dispute=locked, decision_id=final.id, effect_type=effect_type, amount=amount)
        final.save(update_fields=["ledger_entry"])
        appeal = locked.appeal
        appeal.decided_at = now
        appeal.save(update_fields=["decided_at"])
        locked.status = FinancialDispute.Status.CLOSED
        locked.decision_code = code
        locked.decision_summary = reasoning
        locked.closed_at = now
    elif command == "close_no_appeal":
        if locked.status != FinancialDispute.Status.DECIDED:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if locked.appeal_deadline_at is None or locked.appeal_deadline_at > now:
            raise DomainAPIException("DISPUTE_APPEAL_WINDOW_OPEN")
        locked.status = FinancialDispute.Status.CLOSED
        locked.closed_at = now
    else:
        raise DomainAPIException("VALIDATION_ERROR")
    locked.save()
    complete_idempotency(idem, {"dispute_id": str(locked.id)})
    record_audit(
        action=f"platform.dispute.{command}",
        object_type="financial_dispute",
        object_id=locked.id,
        actor_user=actor,
        office_id=locked.booking.office_id,
        request=request,
        before=before,
        after={"status": locked.status, "decision_code": locked.decision_code},
        reason_code=str(data.get("reasoning") or data.get("reason") or command),
    )
    return locked


@transaction.atomic
def office_respond_dispute(
    *,
    dispute: FinancialDispute,
    context: OfficeContext,
    actor: User,
    data: dict[str, Any],
    request: HttpRequest,
    idempotency_key: str,
) -> FinancialDispute:
    locked = FinancialDispute.objects.select_for_update().select_related("booking").get(id=dispute.id)
    if locked.booking.office_id != context.office.id:
        raise DomainAPIException("TENANT_ACCESS_DENIED")
    idem, replay = begin_idempotency(
        scope_type="office_dispute_response", scope_id=locked.id, key=idempotency_key, payload=data
    )
    if replay is not None:
        return FinancialDispute.objects.get(id=replay["dispute_id"])
    evidence = data.get("evidence")
    response = str(data.get("response") or "").strip()
    if locked.status != FinancialDispute.Status.AWAITING_OFFICE:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    if not response or not isinstance(evidence, dict) or not evidence:
        raise DomainAPIException("DISPUTE_EVIDENCE_REQUIRED")
    locked.status = FinancialDispute.Status.UNDER_REVIEW
    locked.save(update_fields=["status"])
    OutboxEvent.objects.create(
        aggregate_type="financial_dispute",
        aggregate_id=locked.id,
        event_type="dispute.office_responded",
        payload={"dispute_id": str(locked.id), "evidence": evidence},
    )
    complete_idempotency(idem, {"dispute_id": str(locked.id)})
    record_audit(
        action="office.dispute.respond",
        object_type="financial_dispute",
        object_id=locked.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"status": locked.status, "evidence_keys": sorted(evidence)},
    )
    return locked


@transaction.atomic
def file_dispute_appeal(
    *,
    dispute: FinancialDispute,
    filed_by_type: str,
    actor: User | None,
    reason: str,
    evidence: dict[str, Any],
    request: HttpRequest | None,
    idempotency_key: str,
) -> FinancialDispute:
    locked = FinancialDispute.objects.select_for_update().select_related("booking").get(id=dispute.id)
    idem, replay = begin_idempotency(
        scope_type="financial_dispute_appeal",
        scope_id=locked.id,
        key=idempotency_key,
        payload={"reason": reason, "evidence": evidence, "filed_by_type": filed_by_type},
    )
    if replay is not None:
        return FinancialDispute.objects.get(id=replay["dispute_id"])
    if (
        locked.status != FinancialDispute.Status.DECIDED
        or locked.appeal_deadline_at is None
        or locked.appeal_deadline_at < timezone.now()
        or hasattr(locked, "appeal")
    ):
        raise DomainAPIException("DISPUTE_APPEAL_NOT_ALLOWED")
    FinancialDisputeAppeal.objects.create(
        dispute=locked, filed_by_type=filed_by_type, filed_by_user=actor, reason=reason, evidence=evidence
    )
    locked.status = FinancialDispute.Status.APPEALED
    locked.appealed_at = timezone.now()
    locked.save(update_fields=["status", "appealed_at"])
    complete_idempotency(idem, {"dispute_id": str(locked.id)})
    record_audit(
        action="dispute.appeal",
        object_type="financial_dispute",
        object_id=locked.id,
        actor_user=actor,
        actor_type="user" if actor else "guest",
        office_id=locked.booking.office_id,
        request=request,
        after={"status": locked.status, "filed_by_type": filed_by_type},
        reason_code=reason,
    )
    return locked
