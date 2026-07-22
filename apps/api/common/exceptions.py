from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from common.context import request_id_context


@dataclass(frozen=True)
class ErrorDefinition:
    code: str
    message: str
    http_status: int
    retryable: bool = False


ERRORS: dict[str, ErrorDefinition] = {
    "AUTH_REQUIRED": ErrorDefinition("AUTH_REQUIRED", "يجب تسجيل الدخول", status.HTTP_401_UNAUTHORIZED),
    "AUTH_INVALID_CREDENTIALS": ErrorDefinition(
        "AUTH_INVALID_CREDENTIALS", "بيانات الدخول غير صحيحة", status.HTTP_401_UNAUTHORIZED
    ),
    "AUTH_MFA_REQUIRED": ErrorDefinition("AUTH_MFA_REQUIRED", "يلزم تحقق إضافي", status.HTTP_403_FORBIDDEN, True),
    "AUTH_MFA_INVALID": ErrorDefinition("AUTH_MFA_INVALID", "رمز التحقق غير صحيح", status.HTTP_403_FORBIDDEN, True),
    "AUTH_SESSION_EXPIRED": ErrorDefinition("AUTH_SESSION_EXPIRED", "انتهت الجلسة", status.HTTP_401_UNAUTHORIZED, True),
    "AUTH_ACCOUNT_SUSPENDED": ErrorDefinition("AUTH_ACCOUNT_SUSPENDED", "الحساب موقوف", status.HTTP_403_FORBIDDEN),
    "PERMISSION_DENIED": ErrorDefinition(
        "PERMISSION_DENIED", "ليس لديك صلاحية لهذا الإجراء", status.HTTP_403_FORBIDDEN
    ),
    "TENANT_ACCESS_DENIED": ErrorDefinition(
        "TENANT_ACCESS_DENIED", "لا يمكن الوصول إلى بيانات هذا المكتب", status.HTTP_403_FORBIDDEN
    ),
    "RESOURCE_NOT_FOUND": ErrorDefinition("RESOURCE_NOT_FOUND", "العنصر غير موجود", status.HTTP_404_NOT_FOUND),
    "VALIDATION_ERROR": ErrorDefinition(
        "VALIDATION_ERROR", "تحقق من البيانات المدخلة", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "RATE_LIMITED": ErrorDefinition(
        "RATE_LIMITED", "محاولات كثيرة، حاول لاحقًا", status.HTTP_429_TOO_MANY_REQUESTS, True
    ),
    "VERIFICATION_INCOMPLETE": ErrorDefinition(
        "VERIFICATION_INCOMPLETE", "ملف التحقق غير مكتمل", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "VERIFICATION_REASON_REQUIRED": ErrorDefinition(
        "VERIFICATION_REASON_REQUIRED", "سبب القرار مطلوب", status.HTTP_422_UNPROCESSABLE_ENTITY
    ),
    "VERIFICATION_CONDITIONS_REQUIRED": ErrorDefinition(
        "VERIFICATION_CONDITIONS_REQUIRED", "شروط الاعتماد المشروط مطلوبة", status.HTTP_422_UNPROCESSABLE_ENTITY
    ),
    "VERIFICATION_NOT_EXPIRED": ErrorDefinition(
        "VERIFICATION_NOT_EXPIRED", "ملف التحقق غير منتهي", status.HTTP_409_CONFLICT
    ),
    "DUAL_APPROVAL_REQUIRED": ErrorDefinition(
        "DUAL_APPROVAL_REQUIRED", "يلزم اعتماد مستخدم ثانٍ", status.HTTP_403_FORBIDDEN
    ),
    "LEGAL_HOLD_ACTIVE": ErrorDefinition(
        "LEGAL_HOLD_ACTIVE", "لا يمكن حذف أو إخفاء البيانات لوجود حجز قانوني", status.HTTP_409_CONFLICT
    ),
    "FILE_TYPE_NOT_ALLOWED": ErrorDefinition(
        "FILE_TYPE_NOT_ALLOWED", "نوع الملف غير مسموح", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "FILE_MALWARE_DETECTED": ErrorDefinition(
        "FILE_MALWARE_DETECTED", "تعذر قبول الملف", status.HTTP_422_UNPROCESSABLE_ENTITY
    ),
    "RISK_MANUAL_REVIEW_REQUIRED": ErrorDefinition(
        "RISK_MANUAL_REVIEW_REQUIRED", "العملية قيد المراجعة الأمنية", status.HTTP_202_ACCEPTED
    ),
    "RISK_BLOCKED": ErrorDefinition(
        "RISK_BLOCKED", "تعذر تنفيذ العملية لأسباب أمنية", status.HTTP_403_FORBIDDEN
    ),
    "CONFIGURATION_OUT_OF_RANGE": ErrorDefinition(
        "CONFIGURATION_OUT_OF_RANGE",
        "قيمة الإعداد خارج الحدود المسموحة",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        True,
    ),
    "STATE_TRANSITION_NOT_ALLOWED": ErrorDefinition(
        "STATE_TRANSITION_NOT_ALLOWED", "انتقال الحالة غير مسموح", status.HTTP_409_CONFLICT
    ),
    "TRIP_NOT_READY": ErrorDefinition(
        "TRIP_NOT_READY", "بيانات الرحلة غير مكتملة", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "TRIP_NOT_BOOKABLE": ErrorDefinition("TRIP_NOT_BOOKABLE", "الرحلة غير متاحة للحجز", status.HTTP_409_CONFLICT),
    "TRIP_INVENTORY_INVALID": ErrorDefinition(
        "TRIP_INVENTORY_INVALID", "مخطط مقاعد الرحلة غير صالح", status.HTTP_409_CONFLICT
    ),
    "TRIP_DEPARTURE_BLOCKED": ErrorDefinition(
        "TRIP_DEPARTURE_BLOCKED", "لا يمكن تسجيل الانطلاق قبل معالجة التعارضات", status.HTTP_409_CONFLICT, True
    ),
    "TRIP_CANCEL_REASON_REQUIRED": ErrorDefinition(
        "TRIP_CANCEL_REASON_REQUIRED", "أدخل سبب إلغاء الرحلة", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "TRIP_UNRESOLVED_CASES": ErrorDefinition(
        "TRIP_UNRESOLVED_CASES", "توجد حالات ركاب غير محسومة", status.HTTP_409_CONFLICT, True
    ),
    "TRIP_NOT_DEPARTED": ErrorDefinition("TRIP_NOT_DEPARTED", "الرحلة لم تنطلق بعد", status.HTTP_409_CONFLICT),
    "OFFICE_NOT_ACTIVE": ErrorDefinition(
        "OFFICE_NOT_ACTIVE", "المكتب غير مفعّل لنشر الرحلات", status.HTTP_403_FORBIDDEN
    ),
    "BOARDING_TOO_EARLY": ErrorDefinition(
        "BOARDING_TOO_EARLY", "لم يحن وقت فتح الصعود", status.HTTP_409_CONFLICT, True
    ),
    "URGENT_CASE_OPEN": ErrorDefinition("URGENT_CASE_OPEN", "توجد حالة عاجلة مفتوحة", status.HTTP_409_CONFLICT, True),
    "SEAT_NOT_AVAILABLE": ErrorDefinition("SEAT_NOT_AVAILABLE", "المقعد لم يعد متاحًا", status.HTTP_409_CONFLICT, True),
    "SEAT_HOLD_EXPIRED": ErrorDefinition(
        "SEAT_HOLD_EXPIRED", "انتهت مهلة الاحتفاظ بالمقعد", status.HTTP_409_CONFLICT, True
    ),
    "SEAT_HOLD_NOT_OWNED": ErrorDefinition(
        "SEAT_HOLD_NOT_OWNED", "الحجز المؤقت لا يخص هذه الجلسة", status.HTTP_403_FORBIDDEN
    ),
    "PASSENGER_GENDER_REQUIRED": ErrorDefinition(
        "PASSENGER_GENDER_REQUIRED",
        "حدد جنس الراكب لاختيار المقعد",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        True,
    ),
    "SEAT_GENDER_CONFLICT": ErrorDefinition(
        "SEAT_GENDER_CONFLICT",
        "المقعد غير متاح وفق سياسة توزيع المقاعد",
        status.HTTP_409_CONFLICT,
        True,
    ),
    "POLICY_ACCEPTANCE_REQUIRED": ErrorDefinition(
        "POLICY_ACCEPTANCE_REQUIRED",
        "يلزم قبول إصدارات السياسات المعروضة",
        status.HTTP_428_PRECONDITION_REQUIRED,
        True,
    ),
    "PRICE_CHANGED": ErrorDefinition(
        "PRICE_CHANGED", "تغير السعر، راجع السعر الجديد قبل المتابعة", status.HTTP_409_CONFLICT, True
    ),
    "SEAT_LAYOUT_MISMATCH": ErrorDefinition("SEAT_LAYOUT_MISMATCH", "مخطط المقاعد غير صالح", status.HTTP_409_CONFLICT),
    "TICKET_QR_INVALID": ErrorDefinition(
        "TICKET_QR_INVALID", "رمز التذكرة غير صالح", status.HTTP_422_UNPROCESSABLE_ENTITY
    ),
    "TICKET_QR_REVOKED": ErrorDefinition(
        "TICKET_QR_REVOKED", "تم إبطال هذا الإصدار من التذكرة", status.HTTP_409_CONFLICT
    ),
    "TICKET_INVALID": ErrorDefinition(
        "TICKET_INVALID", "التذكرة لا تخص هذه الرحلة أو الراكب", status.HTTP_409_CONFLICT
    ),
    "TICKET_ALREADY_USED": ErrorDefinition(
        "TICKET_ALREADY_USED", "تم استخدام التذكرة للصعود مسبقًا", status.HTTP_409_CONFLICT
    ),
    "BOARDING_NOT_OPEN": ErrorDefinition(
        "BOARDING_NOT_OPEN", "الصعود غير مفتوح لهذه الرحلة", status.HTTP_409_CONFLICT, True
    ),
    "BOARDING_REASON_REQUIRED": ErrorDefinition(
        "BOARDING_REASON_REQUIRED", "يلزم تسجيل سبب هذا الإجراء", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "BOARDING_CORRECTION_APPROVAL_REQUIRED": ErrorDefinition(
        "BOARDING_CORRECTION_APPROVAL_REQUIRED",
        "يلزم اعتماد إداري لتصحيح الصعود بعد الانطلاق",
        status.HTTP_403_FORBIDDEN,
    ),
    "NO_SHOW_NOT_ALLOWED": ErrorDefinition(
        "NO_SHOW_NOT_ALLOWED", "لا يمكن تسجيل عدم الحضور لهذه الحالة", status.HTTP_409_CONFLICT
    ),
    "MANIFEST_INTEGRITY_FAILED": ErrorDefinition(
        "MANIFEST_INTEGRITY_FAILED", "فشل التحقق من سلامة قائمة الركاب", status.HTTP_409_CONFLICT
    ),
    "OFFLINE_PACKAGE_INVALID": ErrorDefinition(
        "OFFLINE_PACKAGE_INVALID", "حزمة الصعود دون اتصال غير صالحة", status.HTTP_409_CONFLICT
    ),
    "OFFLINE_PACKAGE_EXPIRED": ErrorDefinition(
        "OFFLINE_PACKAGE_EXPIRED", "انتهت صلاحية حزمة الصعود دون اتصال", status.HTTP_409_CONFLICT
    ),
    "DEVICE_NOT_TRUSTED": ErrorDefinition(
        "DEVICE_NOT_TRUSTED", "يلزم استخدام جهاز مسجل وموثوق", status.HTTP_403_FORBIDDEN
    ),
    "PAYMENT_REQUIRED": ErrorDefinition(
        "PAYMENT_REQUIRED", "يلزم إتمام الدفع أو تسجيله", status.HTTP_402_PAYMENT_REQUIRED, True
    ),
    "SUBSCRIPTION_REQUIRED": ErrorDefinition(
        "SUBSCRIPTION_REQUIRED", "يلزم اشتراك فعال لإجراء عمليات تجارية جديدة", status.HTTP_402_PAYMENT_REQUIRED, True
    ),
    "SUBSCRIPTION_LIMIT_REACHED": ErrorDefinition(
        "SUBSCRIPTION_LIMIT_REACHED", "تم بلوغ حد الاستخدام في الباقة", status.HTTP_409_CONFLICT, True
    ),
    "SUBSCRIPTION_TRIAL_ALREADY_USED": ErrorDefinition(
        "SUBSCRIPTION_TRIAL_ALREADY_USED", "تم استخدام الفترة التجريبية لهذا المكتب سابقًا", status.HTTP_409_CONFLICT
    ),
    "PAYMENT_PROVIDER_UNAVAILABLE": ErrorDefinition(
        "PAYMENT_PROVIDER_UNAVAILABLE", "الدفع الإلكتروني غير متاح مؤقتًا", status.HTTP_503_SERVICE_UNAVAILABLE, True
    ),
    "PAYMENT_AMOUNT_MISMATCH": ErrorDefinition(
        "PAYMENT_AMOUNT_MISMATCH", "مبلغ الدفع أو عملته لا يطابق المطلوب", status.HTTP_409_CONFLICT
    ),
    "PAYMENT_WEBHOOK_INVALID": ErrorDefinition(
        "PAYMENT_WEBHOOK_INVALID", "إشعار دفع غير صالح", status.HTTP_400_BAD_REQUEST
    ),
    "PAYMENT_ALREADY_SUCCEEDED": ErrorDefinition(
        "PAYMENT_ALREADY_SUCCEEDED", "تم تسجيل الدفع مسبقًا", status.HTTP_409_CONFLICT
    ),
    "PAYMENT_STATE_CONFLICT": ErrorDefinition(
        "PAYMENT_STATE_CONFLICT", "حالة الدفع لا تسمح بهذا الإجراء", status.HTTP_409_CONFLICT, True
    ),
    "MANUAL_TRANSFER_DUPLICATE": ErrorDefinition(
        "MANUAL_TRANSFER_DUPLICATE", "مرجع التحويل أو الإثبات مستخدم سابقًا", status.HTTP_409_CONFLICT
    ),
    "MANUAL_TRANSFER_NOT_FOUND": ErrorDefinition(
        "MANUAL_TRANSFER_NOT_FOUND",
        "لم يتم العثور على التحويل في الحساب المستلم",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        True,
    ),
    "PAYMENT_REJECTION_REASON_REQUIRED": ErrorDefinition(
        "PAYMENT_REJECTION_REASON_REQUIRED",
        "أدخل سبب رفض التحويل",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        True,
    ),
    "CANCELLATION_NOT_ALLOWED": ErrorDefinition(
        "CANCELLATION_NOT_ALLOWED", "لا تسمح حالة الحجز أو السياسة بالإلغاء", status.HTTP_409_CONFLICT
    ),
    "CANCELLATION_QUOTE_INVALID": ErrorDefinition(
        "CANCELLATION_QUOTE_INVALID", "عرض الإلغاء غير صالح أو تغير الحجز", status.HTTP_409_CONFLICT, True
    ),
    "CANCELLATION_QUOTE_EXPIRED": ErrorDefinition(
        "CANCELLATION_QUOTE_EXPIRED", "انتهت صلاحية عرض الإلغاء، أعد حسابه", status.HTTP_409_CONFLICT, True
    ),
    "PASSENGER_ALREADY_BOARDED": ErrorDefinition(
        "PASSENGER_ALREADY_BOARDED", "لا يمكن إلغاء أو تعديل راكب صعد إلى الرحلة", status.HTTP_409_CONFLICT
    ),
    "REFUND_AMOUNT_EXCEEDS_AVAILABLE": ErrorDefinition(
        "REFUND_AMOUNT_EXCEEDS_AVAILABLE", "مبلغ الاسترداد يتجاوز المتاح", status.HTTP_422_UNPROCESSABLE_ENTITY
    ),
    "CHARGEBACK_OPEN": ErrorDefinition(
        "CHARGEBACK_OPEN", "يوجد اعتراض دفع مفتوح يمنع التعويض المزدوج", status.HTTP_409_CONFLICT
    ),
    "REFUND_DUPLICATE": ErrorDefinition(
        "REFUND_DUPLICATE", "يوجد طلب استرداد مفتوح لهذا الجزء", status.HTTP_409_CONFLICT
    ),
    "REFUND_STATE_CONFLICT": ErrorDefinition(
        "REFUND_STATE_CONFLICT", "حالة الاسترداد لا تسمح بهذا الإجراء", status.HTTP_409_CONFLICT, True
    ),
    "REFUND_REJECTION_REASON_REQUIRED": ErrorDefinition(
        "REFUND_REJECTION_REASON_REQUIRED", "أدخل سبب رفض الاسترداد", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "REFUND_CONFIRMATION_INVALID": ErrorDefinition(
        "REFUND_CONFIRMATION_INVALID", "إثبات تنفيذ الاسترداد غير صالح", status.HTTP_409_CONFLICT, True
    ),
    "LEDGER_UNBALANCED": ErrorDefinition("LEDGER_UNBALANCED", "القيد المالي غير متوازن", status.HTTP_409_CONFLICT),
    "VERSION_CONFLICT": ErrorDefinition(
        "VERSION_CONFLICT", "تم تعديل العنصر من جلسة أخرى", status.HTTP_409_CONFLICT, True
    ),
    "PAYOUT_ACCOUNT_INVALID": ErrorDefinition(
        "PAYOUT_ACCOUNT_INVALID", "حساب التسوية غير معتمد", status.HTTP_409_CONFLICT, True
    ),
    "SETTLEMENT_PERIOD_OPEN": ErrorDefinition(
        "SETTLEMENT_PERIOD_OPEN", "فترة التسوية لم تغلق بعد", status.HTTP_409_CONFLICT
    ),
    "SETTLEMENT_PAYMENT_UNCONFIRMED": ErrorDefinition(
        "SETTLEMENT_PAYMENT_UNCONFIRMED", "لم يثبت دفع التسوية", status.HTTP_409_CONFLICT, True
    ),
    "SETTLEMENT_DISPUTE_OPEN": ErrorDefinition(
        "SETTLEMENT_DISPUTE_OPEN", "يوجد اعتراض مفتوح على التسوية", status.HTTP_409_CONFLICT
    ),
    "DISPUTE_EVIDENCE_REQUIRED": ErrorDefinition(
        "DISPUTE_EVIDENCE_REQUIRED", "أرفق الأدلة المطلوبة", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "DISPUTE_DECISION_INCOMPLETE": ErrorDefinition(
        "DISPUTE_DECISION_INCOMPLETE", "قرار النزاع غير مكتمل", status.HTTP_422_UNPROCESSABLE_ENTITY, True
    ),
    "DISPUTE_APPEAL_NOT_ALLOWED": ErrorDefinition(
        "DISPUTE_APPEAL_NOT_ALLOWED", "لا يمكن تقديم اعتراض جديد", status.HTTP_409_CONFLICT
    ),
    "DISPUTE_APPEAL_WINDOW_OPEN": ErrorDefinition(
        "DISPUTE_APPEAL_WINDOW_OPEN", "ما زالت مهلة الاعتراض مفتوحة", status.HTTP_409_CONFLICT
    ),
    "DISPUTE_OFFICE_NOT_RESPONSIBLE": ErrorDefinition(
        "DISPUTE_OFFICE_NOT_RESPONSIBLE", "لا يمكن إحالة النزاع إلى هذا المكتب", status.HTTP_409_CONFLICT, True
    ),
    "DISPUTE_SLA_NOT_EXPIRED": ErrorDefinition(
        "DISPUTE_SLA_NOT_EXPIRED", "مهلة رد المكتب لم تنته بعد", status.HTTP_409_CONFLICT
    ),
    "SETTLEMENT_RETRY_BLOCKED": ErrorDefinition(
        "SETTLEMENT_RETRY_BLOCKED", "لا يمكن إعادة محاولة التسوية قبل معالجة السبب", status.HTTP_409_CONFLICT, True
    ),
    "SETTLEMENT_STATE_CONFLICT": ErrorDefinition(
        "SETTLEMENT_STATE_CONFLICT", "حالة التسوية لا تسمح بهذا الإجراء", status.HTTP_409_CONFLICT, True
    ),
    "SETTLEMENT_ITEMS_INVALID": ErrorDefinition(
        "SETTLEMENT_ITEMS_INVALID", "بنود التسوية غير صالحة أو غير متوازنة", status.HTTP_409_CONFLICT, True
    ),
    "SEAT_REALLOCATION_REQUIRED": ErrorDefinition(
        "SEAT_REALLOCATION_REQUIRED",
        "يلزم اختيار مقعد بديل أو معالجة تعارض إعادة التوزيع",
        status.HTTP_409_CONFLICT,
        True,
    ),
    "INCIDENT_NOT_RESOLVED": ErrorDefinition(
        "INCIDENT_NOT_RESOLVED",
        "لم تتم معالجة حقوق جميع الركاب المتأثرين",
        status.HTTP_409_CONFLICT,
        True,
    ),
    "PLATFORM_MAINTENANCE": ErrorDefinition(
        "PLATFORM_MAINTENANCE",
        "المنصة في وضع الصيانة الآمنة",
        status.HTTP_503_SERVICE_UNAVAILABLE,
        True,
    ),
    "DATABASE_UNAVAILABLE": ErrorDefinition(
        "DATABASE_UNAVAILABLE",
        "قاعدة البيانات غير متاحة مؤقتًا",
        status.HTTP_503_SERVICE_UNAVAILABLE,
        True,
    ),
    "RECOVERY_RECONCILIATION_REQUIRED": ErrorDefinition(
        "RECOVERY_RECONCILIATION_REQUIRED",
        "يلزم إكمال مصالحة المقاعد والمدفوعات والدفتر قبل إعادة الفتح",
        status.HTTP_409_CONFLICT,
        True,
    ),
    "RELEASE_ROLLBACK_REQUIRED": ErrorDefinition(
        "RELEASE_ROLLBACK_REQUIRED",
        "فشل الفحص ويلزم مرجع تراجع للإصدار",
        status.HTTP_409_CONFLICT,
    ),
    "INCIDENT_COMMANDER_REQUIRED": ErrorDefinition(
        "INCIDENT_COMMANDER_REQUIRED",
        "يلزم قائد وقناة اتصال للحادث",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
    "INCIDENT_POSTMORTEM_REQUIRED": ErrorDefinition(
        "INCIDENT_POSTMORTEM_REQUIRED",
        "يلزم تقرير ما بعد الحادث قبل إغلاق SEV-1",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ),
    "CONFLICT": ErrorDefinition("CONFLICT", "يوجد تعارض مع بيانات قائمة", status.HTTP_409_CONFLICT),
}


class DomainAPIException(APIException):
    def __init__(
        self,
        code: str,
        *,
        details: list[dict[str, Any]] | dict[str, Any] | None = None,
        message: str | None = None,
        http_status: int | None = None,
        retryable: bool | None = None,
    ) -> None:
        definition = ERRORS.get(code, ErrorDefinition(code, "تعذر إكمال العملية", 400))
        self.status_code = http_status or definition.http_status
        self.code = code
        self.message = message or definition.message
        self.details = details or []
        self.retryable = definition.retryable if retryable is None else retryable
        super().__init__(self.message, code=code)


def error_response(exc: DomainAPIException) -> Response:
    return Response(
        {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id_context.get(),
                "details": exc.details,
                "retryable": exc.retryable,
            }
        },
        status=exc.status_code,
    )


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainAPIException):
        return error_response(exc)

    from rest_framework.views import exception_handler

    response = exception_handler(exc, context)
    if response is None:
        return None

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        wrapped = DomainAPIException("AUTH_REQUIRED")
    elif response.status_code == status.HTTP_403_FORBIDDEN:
        wrapped = DomainAPIException("PERMISSION_DENIED")
    elif response.status_code == status.HTTP_404_NOT_FOUND:
        wrapped = DomainAPIException("RESOURCE_NOT_FOUND")
    elif response.status_code == status.HTTP_400_BAD_REQUEST:
        wrapped = DomainAPIException("VALIDATION_ERROR", details=response.data)
    else:
        wrapped = DomainAPIException(
            "VALIDATION_ERROR",
            details=response.data,
            http_status=response.status_code,
            retryable=response.status_code >= 500,
        )
    return error_response(wrapped)
