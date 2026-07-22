from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.models import OutboxEvent
from finance.models import (
    Commission,
    CommissionProfile,
    FinancialDispute,
    LedgerAccount,
    LedgerEntry,
    LedgerPosting,
    Settlement,
    SettlementItem,
)
from identity.models import User
from organizations.models import Office, OfficePayoutAccount
from organizations.services import OfficeContext, require_fresh_mfa


@dataclass(frozen=True)
class PostingSpec:
    account_code: str
    account_type: str
    direction: str
    amount: Decimal
    office_scoped: bool = False
    memo: str | None = None


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ledger_account(
    *,
    code: str,
    account_type: str,
    currency: str,
    office: Office | None,
) -> LedgerAccount:
    account, _ = LedgerAccount.objects.get_or_create(
        code=code,
        currency=currency,
        office=office,
        defaults={"account_type": account_type},
    )
    if account.account_type != account_type:
        raise DomainAPIException("LEDGER_UNBALANCED", details={"reason": "account_type_conflict"})
    return account


@transaction.atomic
def post_ledger_entry(
    *,
    event_type: str,
    event_id: uuid.UUID,
    currency: str,
    occurred_at: datetime,
    postings: list[PostingSpec],
    description: str,
    office: Office | None = None,
    booking: Booking | None = None,
    trip_id: uuid.UUID | None = None,
    status: str = LedgerEntry.Status.POSTED,
    reversal_of: LedgerEntry | None = None,
) -> LedgerEntry:
    existing = LedgerEntry.objects.filter(
        event_type=event_type,
        event_id=event_id,
        currency=currency,
    ).first()
    if existing is not None:
        return existing

    debit = sum((money(item.amount) for item in postings if item.direction == "D"), Decimal("0.00"))
    credit = sum((money(item.amount) for item in postings if item.direction == "C"), Decimal("0.00"))
    if debit <= 0 or debit != credit:
        raise DomainAPIException(
            "LEDGER_UNBALANCED",
            details={"debit": str(debit), "credit": str(credit)},
        )

    resolved_office = office or (booking.office if booking is not None else None)
    entry = LedgerEntry.objects.create(
        event_type=event_type,
        event_id=event_id,
        booking=booking,
        trip_id=trip_id or (booking.trip_id if booking is not None else None),
        office=resolved_office,
        currency=currency,
        status=status,
        reversal_of=reversal_of,
        occurred_at=occurred_at,
        description=description,
    )
    LedgerPosting.objects.bulk_create(
        [
            LedgerPosting(
                entry=entry,
                account=_ledger_account(
                    code=item.account_code,
                    account_type=item.account_type,
                    currency=currency,
                    office=resolved_office if item.office_scoped else None,
                ),
                direction=item.direction,
                amount=money(item.amount),
                memo=item.memo,
            )
            for item in postings
        ]
    )
    return entry


@transaction.atomic
def post_balanced_entry(
    *,
    event_type: str,
    event_id: uuid.UUID,
    booking: Booking,
    occurred_at: datetime,
    postings: list[PostingSpec],
    description: str,
) -> LedgerEntry:
    return post_ledger_entry(
        event_type=event_type,
        event_id=event_id,
        currency=booking.currency,
        booking=booking,
        occurred_at=occurred_at,
        postings=postings,
        description=description,
    )


def assert_entry_balanced(entry: LedgerEntry) -> None:
    debit = sum(
        (posting.amount for posting in entry.postings.all() if posting.direction == "D"),
        Decimal("0.00"),
    )
    credit = sum(
        (posting.amount for posting in entry.postings.all() if posting.direction == "C"),
        Decimal("0.00"),
    )
    if debit != credit:
        raise DomainAPIException("LEDGER_UNBALANCED")


def create_expected_commission(booking: Booking) -> Commission:
    rules = booking.commission_snapshot.get("rules", {}) if isinstance(booking.commission_snapshot, dict) else {}
    rate = Decimal(str(rules.get("rate", "0")))
    fixed = money(rules.get("fixed_amount", "0"))
    amount = money(booking.total_amount * rate + fixed)
    return Commission.objects.get_or_create(
        booking=booking,
        defaults={
            "office": booking.office,
            "status": Commission.Status.EXPECTED,
            "basis_amount": booking.total_amount,
            "rate": rate,
            "fixed_amount": fixed,
            "commission_amount": amount,
            "currency": booking.currency,
        },
    )[0]


def post_direct_payment_entry(
    *, transaction_id: uuid.UUID, booking: Booking, amount: Decimal, occurred_at: datetime
) -> LedgerEntry:
    return post_balanced_entry(
        event_type="DIRECT_PAYMENT_COLLECTED",
        event_id=transaction_id,
        booking=booking,
        occurred_at=occurred_at,
        description="Direct office cash or transfer collected for customer booking",
        postings=[
            PostingSpec(
                account_code="1100_OFFICE_CASH_CUSTODY",
                account_type=LedgerAccount.AccountType.ASSET,
                direction=LedgerPosting.Direction.DEBIT,
                amount=amount,
                office_scoped=True,
            ),
            PostingSpec(
                account_code="2000_CUSTOMER_FUNDS",
                account_type=LedgerAccount.AccountType.LIABILITY,
                direction=LedgerPosting.Direction.CREDIT,
                amount=amount,
                office_scoped=True,
            ),
        ],
    )


def post_electronic_capture_entry(
    *, transaction_id: uuid.UUID, booking: Booking, amount: Decimal, occurred_at: datetime
) -> LedgerEntry:
    return post_balanced_entry(
        event_type="ELECTRONIC_PAYMENT_CAPTURED",
        event_id=transaction_id,
        booking=booking,
        occurred_at=occurred_at,
        description="Electronic payment captured by provider",
        postings=[
            PostingSpec(
                account_code="1010_PSP_RECEIVABLE",
                account_type=LedgerAccount.AccountType.ASSET,
                direction=LedgerPosting.Direction.DEBIT,
                amount=amount,
            ),
            PostingSpec(
                account_code="2000_CUSTOMER_FUNDS",
                account_type=LedgerAccount.AccountType.LIABILITY,
                direction=LedgerPosting.Direction.CREDIT,
                amount=amount,
            ),
        ],
    )


def adjust_commission_after_booking_change(booking: Booking) -> Commission:
    commission = Commission.objects.select_for_update().filter(booking=booking).first()
    if commission is None:
        return create_expected_commission(booking)
    original_basis = money(commission.basis_amount)
    new_basis = money(booking.total_amount)
    if new_basis <= 0:
        commission.basis_amount = Decimal("0.00")
        commission.fixed_amount = Decimal("0.00")
        commission.commission_amount = Decimal("0.00")
        commission.status = Commission.Status.REVERSED
    else:
        ratio = Decimal("1.00") if original_basis <= 0 else min(Decimal("1.00"), new_basis / original_basis)
        commission.basis_amount = new_basis
        commission.fixed_amount = money(commission.fixed_amount * ratio)
        commission.commission_amount = money(new_basis * commission.rate + commission.fixed_amount)
        commission.status = Commission.Status.ADJUSTED
    commission.save(update_fields=["basis_amount", "fixed_amount", "commission_amount", "status"])
    return commission


def post_refund_approved_entry(
    *, refund_id: uuid.UUID, booking: Booking, amount: Decimal, occurred_at: datetime
) -> LedgerEntry:
    return post_balanced_entry(
        event_type="REFUND_APPROVED",
        event_id=refund_id,
        booking=booking,
        occurred_at=occurred_at,
        description="Approved refund reclassified from customer funds to refund payable",
        postings=[
            PostingSpec(
                account_code="2000_CUSTOMER_FUNDS",
                account_type=LedgerAccount.AccountType.LIABILITY,
                direction=LedgerPosting.Direction.DEBIT,
                amount=amount,
                office_scoped=True,
            ),
            PostingSpec(
                account_code="2100_REFUND_PAYABLE",
                account_type=LedgerAccount.AccountType.LIABILITY,
                direction=LedgerPosting.Direction.CREDIT,
                amount=amount,
                office_scoped=True,
            ),
        ],
    )


def post_refund_succeeded_entry(
    *,
    refund_id: uuid.UUID,
    booking: Booking,
    amount: Decimal,
    occurred_at: datetime,
    electronic: bool,
) -> LedgerEntry:
    asset_code = "1010_PSP_RECEIVABLE" if electronic else "1100_OFFICE_CASH_CUSTODY"
    return post_balanced_entry(
        event_type="REFUND_SUCCEEDED",
        event_id=refund_id,
        booking=booking,
        occurred_at=occurred_at,
        description="Refund paid to customer",
        postings=[
            PostingSpec(
                account_code="2100_REFUND_PAYABLE",
                account_type=LedgerAccount.AccountType.LIABILITY,
                direction=LedgerPosting.Direction.DEBIT,
                amount=amount,
                office_scoped=True,
            ),
            PostingSpec(
                account_code=asset_code,
                account_type=LedgerAccount.AccountType.ASSET,
                direction=LedgerPosting.Direction.CREDIT,
                amount=amount,
                office_scoped=not electronic,
            ),
        ],
    )


def _successful_payment_method(booking: Booking) -> str | None:
    from payments.models import PaymentIntent

    return (
        PaymentIntent.objects.filter(booking=booking, status=PaymentIntent.Status.SUCCEEDED)
        .order_by("-updated_at")
        .values_list("method_type", flat=True)
        .first()
    )


@transaction.atomic
def recognize_booking_service(*, booking: Booking, occurred_at: datetime | None = None) -> Commission:
    locked = Booking.objects.select_for_update().select_related("office", "trip").get(id=booking.id)
    commission = Commission.objects.select_for_update().filter(booking=locked).first()
    if commission is None:
        commission = create_expected_commission(locked)
    if commission.status in {
        Commission.Status.EARNED,
        Commission.Status.IN_SETTLEMENT,
        Commission.Status.PAID,
    }:
        return commission
    if locked.payment_status not in {
        Booking.PaymentStatus.PAID,
        Booking.PaymentStatus.PARTIALLY_REFUNDED,
    }:
        raise DomainAPIException("PAYMENT_REQUIRED")
    if locked.trip.status != "completed" and locked.status != Booking.Status.NO_SHOW:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED", details={"reason": "service_not_completed"})

    method = _successful_payment_method(locked)
    if method is None:
        raise DomainAPIException("PAYMENT_REQUIRED")
    gross = money(max(Decimal("0.00"), locked.paid_amount - locked.refunded_amount))
    commission_amount = min(money(commission.commission_amount), gross)
    office_net = money(gross - commission_amount)
    when = occurred_at or locked.trip.actual_arrival_at or timezone.now()

    if method == "electronic":
        postings: list[PostingSpec] = [
            PostingSpec(
                account_code="2000_CUSTOMER_FUNDS",
                account_type=LedgerAccount.AccountType.LIABILITY,
                direction=LedgerPosting.Direction.DEBIT,
                amount=gross,
            )
        ]
        if office_net > 0:
            postings.append(
                PostingSpec(
                    account_code="2010_OFFICE_PAYABLE",
                    account_type=LedgerAccount.AccountType.LIABILITY,
                    direction=LedgerPosting.Direction.CREDIT,
                    amount=office_net,
                    office_scoped=True,
                )
            )
        if commission_amount > 0:
            postings.append(
                PostingSpec(
                    account_code="4000_COMMISSION_REVENUE",
                    account_type=LedgerAccount.AccountType.REVENUE,
                    direction=LedgerPosting.Direction.CREDIT,
                    amount=commission_amount,
                )
            )
        post_balanced_entry(
            event_type="SERVICE_COMPLETED_ELECTRONIC",
            event_id=locked.id,
            booking=locked,
            occurred_at=when,
            description="Completed electronic booking recognized as office payable and commission revenue",
            postings=postings,
        )
    else:
        postings = []
        if gross > 0:
            postings.extend(
                [
                    PostingSpec(
                        account_code="2000_CUSTOMER_FUNDS",
                        account_type=LedgerAccount.AccountType.LIABILITY,
                        direction=LedgerPosting.Direction.DEBIT,
                        amount=gross,
                        office_scoped=True,
                    ),
                    PostingSpec(
                        account_code="1100_OFFICE_CASH_CUSTODY",
                        account_type=LedgerAccount.AccountType.ASSET,
                        direction=LedgerPosting.Direction.CREDIT,
                        amount=gross,
                        office_scoped=True,
                    ),
                ]
            )
        if commission_amount > 0:
            postings.extend(
                [
                    PostingSpec(
                        account_code="1020_OFFICE_COMMISSION_RECEIVABLE",
                        account_type=LedgerAccount.AccountType.ASSET,
                        direction=LedgerPosting.Direction.DEBIT,
                        amount=commission_amount,
                        office_scoped=True,
                    ),
                    PostingSpec(
                        account_code="4000_COMMISSION_REVENUE",
                        account_type=LedgerAccount.AccountType.REVENUE,
                        direction=LedgerPosting.Direction.CREDIT,
                        amount=commission_amount,
                    ),
                ]
            )
        if postings:
            post_balanced_entry(
                event_type="COMMISSION_EARNED_DIRECT",
                event_id=locked.id,
                booking=locked,
                occurred_at=when,
                description="Completed direct-office booking cleared custody and earned commission receivable",
                postings=postings,
            )

    commission.status = Commission.Status.EARNED
    commission.earned_at = when
    commission.save(update_fields=["status", "earned_at"])
    if locked.status == Booking.Status.CONFIRMED:
        locked.status = Booking.Status.COMPLETED
        locked.save(update_fields=["status", "updated_at"])
    OutboxEvent.objects.create(
        aggregate_type="commission",
        aggregate_id=commission.id,
        event_type="commission.earned",
        payload={
            "booking_id": locked.public_id,
            "office_id": locked.office.public_id,
            "currency": locked.currency,
            "amount": str(commission_amount),
            "payment_method": method,
        },
    )
    return commission


@transaction.atomic
def recognize_trip_financials(*, trip_id: uuid.UUID) -> int:
    from trips.models import Trip

    trip = Trip.objects.select_for_update().get(id=trip_id)
    if trip.status != Trip.Status.COMPLETED:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED", details={"reason": "trip_not_completed"})
    bookings = Booking.objects.filter(
        trip=trip,
        status__in=[Booking.Status.CONFIRMED, Booking.Status.NO_SHOW, Booking.Status.COMPLETED],
        payment_status__in=[Booking.PaymentStatus.PAID, Booking.PaymentStatus.PARTIALLY_REFUNDED],
    )
    count = 0
    for booking in bookings:
        recognize_booking_service(booking=booking, occurred_at=trip.actual_arrival_at or timezone.now())
        count += 1
    return count


@transaction.atomic
def reverse_ledger_entry(
    *, original: LedgerEntry, event_id: uuid.UUID, description: str, actor: User | None = None,
    request: HttpRequest | None = None,
) -> LedgerEntry:
    locked = LedgerEntry.objects.select_for_update().prefetch_related("postings__account").get(id=original.id)
    if locked.reversals.exists():
        return locked.reversals.order_by("posted_at").first()  # type: ignore[return-value]
    reversal = post_ledger_entry(
        event_type=f"{locked.event_type}_REVERSAL",
        event_id=event_id,
        currency=locked.currency,
        office=locked.office,
        booking=locked.booking,
        trip_id=locked.trip_id,
        occurred_at=timezone.now(),
        description=description,
        status=LedgerEntry.Status.REVERSED,
        reversal_of=locked,
        postings=[
            PostingSpec(
                account_code=posting.account.code,
                account_type=posting.account.account_type,
                direction=(
                    LedgerPosting.Direction.CREDIT
                    if posting.direction == LedgerPosting.Direction.DEBIT
                    else LedgerPosting.Direction.DEBIT
                ),
                amount=posting.amount,
                office_scoped=posting.account.office_id is not None,
                memo=f"Reversal of {locked.id}",
            )
            for posting in locked.postings.all()
        ],
    )
    record_audit(
        action="finance.ledger.reverse",
        object_type="ledger_entry",
        object_id=locked.id,
        actor_user=actor,
        actor_type="system" if actor is None else "user",
        office_id=locked.office_id,
        request=request,
        before={"status": locked.status, "event_type": locked.event_type},
        after={"reversal_entry_id": str(reversal.id)},
    )
    return reversal


def serialize_settlement(settlement: Settlement) -> dict[str, Any]:
    return {
        "id": settlement.public_id,
        "office_id": settlement.office.public_id,
        "period_start": settlement.period_start,
        "period_end": settlement.period_end,
        "currency": settlement.currency,
        "status": settlement.status,
        "gross_amount": str(settlement.gross_amount),
        "commission_amount": str(settlement.commission_amount),
        "refund_amount": str(settlement.refund_amount),
        "reserve_amount": str(settlement.reserve_amount),
        "adjustment_amount": str(settlement.adjustment_amount),
        "net_amount": str(settlement.net_amount),
        "created_by": str(settlement.created_by_id),
        "approved_by": str(settlement.approved_by_id) if settlement.approved_by_id else None,
        "payment_reference": settlement.payment_reference,
        "created_at": settlement.created_at,
        "paid_at": settlement.paid_at,
        "items": [
            {
                "id": str(item.id),
                "type": item.item_type,
                "source_type": item.source_type,
                "source_id": str(item.source_id),
                "booking_id": item.booking.public_id if item.booking_id and item.booking is not None else None,
                "amount": str(item.amount),
                "currency": item.currency,
                "description": item.description,
            }
            for item in settlement.items.select_related("booking").order_by("created_at", "id")
        ],
    }


@transaction.atomic
def create_settlement(
    *, actor: User, office_id: str, period_start: date, period_end: date, currency: str,
    idempotency_key: str, request: HttpRequest | None,
) -> Settlement:
    office = Office.objects.filter(public_id=office_id).first()
    if office is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if period_end < period_start:
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "period_end", "reason": "before_start"}])
    if period_end >= timezone.localdate():
        raise DomainAPIException("SETTLEMENT_PERIOD_OPEN", details={"period_end": period_end.isoformat()})
    record, replay = begin_idempotency(
        scope_type="platform_settlement_create",
        scope_id=office.id,
        key=idempotency_key,
        payload={
            "office_id": office_id,
            "period_start": period_start,
            "period_end": period_end,
            "currency": currency.upper(),
        },
    )
    if replay is not None:
        return Settlement.objects.get(id=replay["settlement_id"])
    settlement, created = Settlement.objects.get_or_create(
        office=office,
        period_start=period_start,
        period_end=period_end,
        currency=currency.upper(),
        defaults={"created_by": actor},
    )
    if not created and settlement.created_by_id != actor.id:
        raise DomainAPIException("CONFLICT", details={"reason": "settlement_period_exists"})
    complete_idempotency(record, {"settlement_id": str(settlement.id)})
    record_audit(
        action="platform.settlement.create",
        object_type="settlement",
        object_id=settlement.id,
        actor_user=actor,
        office_id=office.id,
        request=request,
        after={"period_start": str(period_start), "period_end": str(period_end), "currency": currency.upper()},
    )
    return settlement


def _open_disputed_amount(booking: Booking, currency: str) -> Decimal:
    total = sum(
        (
            money(dispute.disputed_amount or booking.total_amount)
            for dispute in booking.financial_disputes.filter(
                status__in=[FinancialDispute.Status.OPEN, FinancialDispute.Status.UNDER_REVIEW],
                currency=currency,
            )
        ),
        Decimal("0.00"),
    )
    return money(total)


@transaction.atomic
def calculate_settlement(settlement: Settlement) -> Settlement:
    locked = Settlement.objects.select_for_update().select_related("office").get(id=settlement.id)
    if locked.status not in {Settlement.Status.DRAFT, Settlement.Status.CALCULATED}:
        raise DomainAPIException("SETTLEMENT_STATE_CONFLICT")

    previous_commissions = Commission.objects.filter(settlement_items__settlement=locked).distinct()
    previous_commissions.update(status=Commission.Status.EARNED)
    locked.items.all().delete()

    commissions = list(
        Commission.objects.select_for_update()
        .select_related("booking", "booking__trip")
        .filter(
            office=locked.office,
            currency=locked.currency,
            status=Commission.Status.EARNED,
            earned_at__date__gte=locked.period_start,
            earned_at__date__lte=locked.period_end,
        )
        .order_by("earned_at", "id")
    )
    gross = Decimal("0.00")
    commission_total = Decimal("0.00")
    refunds = Decimal("0.00")
    frozen_total = Decimal("0.00")
    electronic_available = Decimal("0.00")
    direct_commission = Decimal("0.00")

    from payments.models import PaymentIntent

    for commission in commissions:
        booking = commission.booking
        method = _successful_payment_method(booking)
        if method is None:
            continue
        recognized_gross = money(max(Decimal("0.00"), booking.paid_amount - booking.refunded_amount))
        commission_amount = min(money(commission.commission_amount), recognized_gross)
        commission_total += commission_amount
        refunds += money(booking.refunded_amount)
        if method == PaymentIntent.MethodType.ELECTRONIC:
            office_net = money(recognized_gross - commission_amount)
            disputed = min(office_net, _open_disputed_amount(booking, locked.currency))
            payable = money(office_net - disputed)
            gross += recognized_gross
            electronic_available += payable
            SettlementItem.objects.create(
                settlement=locked,
                item_type=SettlementItem.ItemType.ELECTRONIC_PAYABLE,
                source_type="commission",
                source_id=commission.id,
                booking=booking,
                commission=commission,
                amount=office_net,
                currency=locked.currency,
                description="Office payable after platform commission",
            )
            if disputed > 0:
                frozen_total += disputed
                dispute = booking.financial_disputes.filter(
                    status__in=[FinancialDispute.Status.OPEN, FinancialDispute.Status.UNDER_REVIEW],
                    currency=locked.currency,
                ).order_by("opened_at").first()
                SettlementItem.objects.create(
                    settlement=locked,
                    item_type=SettlementItem.ItemType.FROZEN_DISPUTE,
                    source_type="dispute",
                    source_id=dispute.id if dispute is not None else booking.id,
                    booking=booking,
                    commission=commission,
                    amount=disputed,
                    currency=locked.currency,
                    description="Only the disputed booking amount is frozen",
                )
        else:
            direct_commission += commission_amount
            SettlementItem.objects.create(
                settlement=locked,
                item_type=SettlementItem.ItemType.DIRECT_COMMISSION,
                source_type="commission",
                source_id=commission.id,
                booking=booking,
                commission=commission,
                amount=commission_amount,
                currency=locked.currency,
                description="Commission receivable from direct office collection",
            )
        commission.status = Commission.Status.IN_SETTLEMENT
        commission.save(update_fields=["status"])

    netted = min(electronic_available, direct_commission)
    if netted > 0:
        SettlementItem.objects.create(
            settlement=locked,
            item_type=SettlementItem.ItemType.NETTING,
            source_type="settlement",
            source_id=locked.id,
            amount=money(netted),
            currency=locked.currency,
            description="Same-currency netting between office payable and direct commission receivable",
        )

    locked.gross_amount = money(gross)
    locked.commission_amount = money(commission_total)
    locked.refund_amount = money(refunds)
    locked.reserve_amount = money(frozen_total)
    locked.adjustment_amount = Decimal("0.00")
    locked.net_amount = money(electronic_available - direct_commission)
    locked.status = Settlement.Status.CALCULATED
    locked.calculated_at = timezone.now()
    locked.save()
    return locked


def _active_payout_account(settlement: Settlement) -> OfficePayoutAccount | None:
    return settlement.office.payout_accounts.filter(
        status=OfficePayoutAccount.Status.ACTIVE,
        effective_at__lte=timezone.now(),
    ).first()


@transaction.atomic
def command_settlement(
    *, settlement: Settlement, actor: User, command: str, payment_reference: str | None,
    idempotency_key: str, request: HttpRequest,
) -> Settlement:
    locked = Settlement.objects.select_for_update().select_related("office", "created_by").get(id=settlement.id)
    record, replay = begin_idempotency(
        scope_type="platform_settlement_command",
        scope_id=locked.id,
        key=idempotency_key,
        payload={"command": command, "payment_reference": payment_reference},
    )
    if replay is not None:
        return Settlement.objects.get(id=replay["settlement_id"])
    before = locked.status
    now = timezone.now()

    if command == "calculate":
        locked = calculate_settlement(locked)
    elif command == "submit_review":
        if locked.status != Settlement.Status.CALCULATED:
            raise DomainAPIException("SETTLEMENT_STATE_CONFLICT")
        locked.status = Settlement.Status.UNDER_REVIEW
        locked.save(update_fields=["status", "updated_at"])
    elif command == "approve":
        if locked.status != Settlement.Status.UNDER_REVIEW:
            raise DomainAPIException("SETTLEMENT_STATE_CONFLICT")
        if locked.created_by_id == actor.id:
            raise DomainAPIException("DUAL_APPROVAL_REQUIRED")
        require_fresh_mfa(request)
        if locked.net_amount > 0 and _active_payout_account(locked) is None:
            raise DomainAPIException("PAYOUT_ACCOUNT_INVALID")
        locked.status = Settlement.Status.APPROVED
        locked.approved_by = actor
        locked.approved_at = now
        locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    elif command == "process":
        if locked.status != Settlement.Status.APPROVED:
            raise DomainAPIException("SETTLEMENT_STATE_CONFLICT")
        locked.status = Settlement.Status.PROCESSING
        locked.processing_started_at = now
        locked.failure_reason = None
        locked.save(update_fields=["status", "processing_started_at", "failure_reason", "updated_at"])
    elif command == "retry":
        if locked.status != Settlement.Status.FAILED:
            raise DomainAPIException("SETTLEMENT_RETRY_BLOCKED")
        locked.status = Settlement.Status.PROCESSING
        locked.processing_started_at = now
        locked.failure_reason = None
        locked.save(update_fields=["status", "processing_started_at", "failure_reason", "updated_at"])
    elif command == "mark_paid":
        if locked.status != Settlement.Status.PROCESSING:
            raise DomainAPIException("SETTLEMENT_STATE_CONFLICT")
        reference = str(payment_reference or "").strip()
        if not reference:
            raise DomainAPIException("SETTLEMENT_PAYMENT_UNCONFIRMED")
        if locked.net_amount > 0 and _active_payout_account(locked) is None:
            raise DomainAPIException("PAYOUT_ACCOUNT_INVALID")
        netting = money(
            sum(
                (item.amount for item in locked.items.filter(item_type=SettlementItem.ItemType.NETTING)),
                Decimal("0.00"),
            )
        )
        if netting > 0:
            post_ledger_entry(
                event_type="DIRECT_COMMISSION_NETTED",
                event_id=locked.id,
                currency=locked.currency,
                office=locked.office,
                occurred_at=now,
                description="Same-currency commission receivable netted against office payable",
                postings=[
                    PostingSpec(
                        account_code="2010_OFFICE_PAYABLE",
                        account_type=LedgerAccount.AccountType.LIABILITY,
                        direction=LedgerPosting.Direction.DEBIT,
                        amount=netting,
                        office_scoped=True,
                    ),
                    PostingSpec(
                        account_code="1020_OFFICE_COMMISSION_RECEIVABLE",
                        account_type=LedgerAccount.AccountType.ASSET,
                        direction=LedgerPosting.Direction.CREDIT,
                        amount=netting,
                        office_scoped=True,
                    ),
                ],
            )
        if locked.net_amount > 0:
            post_ledger_entry(
                event_type="SETTLEMENT_PAID",
                event_id=locked.id,
                currency=locked.currency,
                office=locked.office,
                occurred_at=now,
                description=f"Settlement payout {reference}",
                postings=[
                    PostingSpec(
                        account_code="2010_OFFICE_PAYABLE",
                        account_type=LedgerAccount.AccountType.LIABILITY,
                        direction=LedgerPosting.Direction.DEBIT,
                        amount=locked.net_amount,
                        office_scoped=True,
                    ),
                    PostingSpec(
                        account_code="1000_BANK",
                        account_type=LedgerAccount.AccountType.ASSET,
                        direction=LedgerPosting.Direction.CREDIT,
                        amount=locked.net_amount,
                    ),
                ],
            )
        elif locked.net_amount < 0:
            amount_due = money(abs(locked.net_amount))
            post_ledger_entry(
                event_type="OFFICE_COMMISSION_PAID",
                event_id=locked.id,
                currency=locked.currency,
                office=locked.office,
                occurred_at=now,
                description=f"Office paid net commission balance {reference}",
                postings=[
                    PostingSpec(
                        account_code="1000_BANK",
                        account_type=LedgerAccount.AccountType.ASSET,
                        direction=LedgerPosting.Direction.DEBIT,
                        amount=amount_due,
                    ),
                    PostingSpec(
                        account_code="1020_OFFICE_COMMISSION_RECEIVABLE",
                        account_type=LedgerAccount.AccountType.ASSET,
                        direction=LedgerPosting.Direction.CREDIT,
                        amount=amount_due,
                        office_scoped=True,
                    ),
                ],
            )
        locked.status = Settlement.Status.PAID
        locked.payment_reference = reference
        locked.paid_at = now
        locked.save(update_fields=["status", "payment_reference", "paid_at", "updated_at"])
        Commission.objects.filter(settlement_items__settlement=locked).distinct().update(status=Commission.Status.PAID)
    elif command == "close":
        if locked.status != Settlement.Status.PAID:
            raise DomainAPIException("SETTLEMENT_STATE_CONFLICT")
        locked.status = Settlement.Status.CLOSED
        locked.closed_at = now
        locked.save(update_fields=["status", "closed_at", "updated_at"])
    else:
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "command", "reason": "unsupported"}])

    complete_idempotency(record, {"settlement_id": str(locked.id)})
    OutboxEvent.objects.create(
        aggregate_type="settlement",
        aggregate_id=locked.id,
        event_type=f"settlement.{command}",
        payload={"settlement_id": locked.public_id, "office_id": locked.office.public_id, "status": locked.status},
    )
    record_audit(
        action=f"platform.settlement.{command}",
        object_type="settlement",
        object_id=locked.id,
        actor_user=actor,
        office_id=locked.office_id,
        request=request,
        before={"status": before},
        after={"status": locked.status, "net_amount": str(locked.net_amount)},
    )
    return locked


def list_office_settlements(context: OfficeContext) -> list[dict[str, Any]]:
    query = (
        Settlement.objects.filter(office=context.office)
        .select_related("office", "created_by")
        .order_by("-period_end")
    )
    return [serialize_settlement(item) for item in query]


def list_platform_settlements(*, status: str | None = None, office_id: str | None = None) -> list[dict[str, Any]]:
    query = Settlement.objects.select_related("office", "created_by", "approved_by").all()
    if status:
        query = query.filter(status=status)
    if office_id:
        query = query.filter(office__public_id=office_id)
    return [serialize_settlement(item) for item in query.order_by("-period_end", "office__name")]


def serialize_commission_profile(profile: CommissionProfile) -> dict[str, Any]:
    return {
        "id": profile.public_id,
        "code": profile.code,
        "name": profile.name,
        "calculation_type": profile.calculation_type,
        "percentage_rate": str(profile.percentage_rate),
        "fixed_amount": str(profile.fixed_amount),
        "currency": profile.currency,
        "status": profile.status,
        "version": profile.version,
        "effective_from": profile.effective_from,
    }


@transaction.atomic
def create_commission_profile(
    *, actor: User, request: HttpRequest, data: dict[str, Any], idempotency_key: str
) -> CommissionProfile:
    require_fresh_mfa(request)
    code = str(data["code"]).strip().upper()
    record, replay = begin_idempotency(
        scope_type="commission_profile_create",
        scope_id=None,
        key=idempotency_key,
        payload=data,
    )
    if replay is not None:
        return CommissionProfile.objects.get(id=replay["profile_id"])
    if CommissionProfile.objects.filter(code=code).exists():
        raise DomainAPIException("CONFLICT", details={"reason": "commission_profile_code_exists"})
    status_value = str(data.get("status", CommissionProfile.Status.DRAFT))
    if status_value not in CommissionProfile.Status.values:
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "status", "reason": "invalid"}])
    profile = CommissionProfile.objects.create(
        code=code,
        name=str(data["name"]).strip(),
        calculation_type=str(data["calculation_type"]),
        percentage_rate=Decimal(str(data.get("percentage_rate", "0"))),
        fixed_amount=money(data.get("fixed_amount", "0")),
        currency=str(data.get("currency") or "").upper() or None,
        status=status_value,
        effective_from=data.get("effective_from"),
        created_by=actor,
        approved_by=actor if data.get("status") == CommissionProfile.Status.ACTIVE else None,
    )
    complete_idempotency(record, {"profile_id": str(profile.id)})
    OutboxEvent.objects.create(
        aggregate_type="commission_profile",
        aggregate_id=profile.id,
        event_type="commission_profile.created",
        payload={"profile_id": profile.public_id, "code": profile.code, "version": profile.version},
    )
    record_audit(
        action="platform.commission_profile.create",
        object_type="commission_profile",
        object_id=profile.id,
        actor_user=actor,
        request=request,
        after=serialize_commission_profile(profile),
    )
    return profile


@transaction.atomic
def update_commission_profile(
    *, profile: CommissionProfile, actor: User, request: HttpRequest, data: dict[str, Any], idempotency_key: str
) -> CommissionProfile:
    require_fresh_mfa(request)
    current = CommissionProfile.objects.select_for_update().get(id=profile.id)
    expected_version = int(data.get("version", current.version))
    if expected_version != current.version:
        raise DomainAPIException("VERSION_CONFLICT")
    record, replay = begin_idempotency(
        scope_type="commission_profile_update",
        scope_id=current.id,
        key=idempotency_key,
        payload=data,
    )
    if replay is not None:
        return CommissionProfile.objects.get(id=replay["profile_id"])
    status_value = str(data.get("status", CommissionProfile.Status.DRAFT))
    if status_value not in CommissionProfile.Status.values:
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "status", "reason": "invalid"}])
    next_profile = CommissionProfile.objects.create(
        code=current.code,
        name=str(data.get("name", current.name)).strip(),
        calculation_type=str(data.get("calculation_type", current.calculation_type)),
        percentage_rate=Decimal(str(data.get("percentage_rate", current.percentage_rate))),
        fixed_amount=money(data.get("fixed_amount", current.fixed_amount)),
        currency=str(data.get("currency", current.currency) or "").upper() or None,
        status=status_value,
        version=current.version + 1,
        effective_from=data.get("effective_from", current.effective_from),
        supersedes=current,
        created_by=actor,
        approved_by=actor if data.get("status") == CommissionProfile.Status.ACTIVE else None,
    )
    if next_profile.status == CommissionProfile.Status.ACTIVE:
        CommissionProfile.objects.filter(code=current.code, status=CommissionProfile.Status.ACTIVE).exclude(
            id=next_profile.id
        ).update(status=CommissionProfile.Status.RETIRED)
    complete_idempotency(record, {"profile_id": str(next_profile.id)})
    OutboxEvent.objects.create(
        aggregate_type="commission_profile",
        aggregate_id=next_profile.id,
        event_type="commission_profile.version_created",
        payload={
            "profile_id": next_profile.public_id,
            "code": next_profile.code,
            "version": next_profile.version,
            "supersedes_id": current.public_id,
        },
    )
    record_audit(
        action="platform.commission_profile.version_create",
        object_type="commission_profile",
        object_id=next_profile.id,
        actor_user=actor,
        request=request,
        before=serialize_commission_profile(current),
        after=serialize_commission_profile(next_profile),
    )
    return next_profile
