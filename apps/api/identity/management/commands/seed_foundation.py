from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from identity.models import Permission, Role, RolePermission

PERMISSIONS = {
    "office.trip.manage": ("إدارة الرحلات", "sensitive"),
    "office.booking.create": ("إنشاء الحجوزات", "normal"),
    "office.payment.confirm_manual": ("تأكيد الدفع اليدوي", "critical"),
    "office.boarding.scan": ("مسح تذاكر الصعود", "normal"),
    "office.finance.view": ("عرض البيانات المالية", "sensitive"),
    "office.refund.request": ("طلب استرداد", "sensitive"),
    "office.refund.approve": ("اعتماد استرداد", "critical"),
    "office.branch.manage": ("إدارة فروع المكتب", "sensitive"),
    "office.staff.manage": ("إدارة موظفي المكتب", "critical"),
    "office.verification.manage": ("إدارة ملف تحقق المكتب", "sensitive"),
    "office.fleet.manage": ("إدارة الأسطول ومخططات المقاعد", "sensitive"),
    "office.payout.manage": ("طلب تغيير حساب التسوية", "critical"),
    "office.payout.approve": ("اعتماد تغيير حساب التسوية", "critical"),
    "office.support.manage": ("إدارة الدعم والحوادث التشغيلية", "sensitive"),
    "office.configuration.manage": ("إدارة إعدادات المكتب", "critical"),
    "platform.office.verify": ("اعتماد المكاتب", "critical"),
    "platform.catalog.manage": ("إدارة المواقع والمسارات", "sensitive"),
    "platform.policy.manage": ("إدارة إصدارات السياسات", "critical"),
    "platform.settlement.approve": ("اعتماد التسويات", "critical"),
    "platform.settlement.manage": ("إدارة دورات التسوية", "critical"),
    "platform.commission.manage": ("إدارة ملفات العمولات", "critical"),
    "platform.audit.view": ("عرض سجل التدقيق", "sensitive"),
    "platform.support.manage": ("إدارة الدعم والتصعيد", "sensitive"),
    "platform.trip.incident.manage": ("إدارة حوادث الرحلات", "critical"),
    "platform.configuration.manage": ("إدارة إعدادات المنصة", "critical"),
    "platform.office.manage": ("إدارة حالة المكاتب", "critical"),
    "platform.violation.manage": ("إدارة مخالفات المكاتب", "critical"),
    "platform.report.view": ("عرض تقارير المنصة", "sensitive"),
    "office.report.view": ("عرض تقارير المكتب", "sensitive"),
    "platform.notification.manage": ("إدارة تسليم الإشعارات", "sensitive"),
    "office.notification.view": ("عرض إشعارات المكتب", "normal"),
    "platform.risk.view": ("عرض تقييمات المخاطر", "sensitive"),
    "platform.privacy.manage": ("إدارة الحجز القانوني وطلبات الخصوصية", "critical"),
    "platform.dispute.manage": ("إدارة النزاعات وقراراتها", "sensitive"),
    "platform.dispute.finance": ("تنفيذ الأثر المالي لقرارات النزاع", "critical"),
    "platform.approval.manage": ("اعتماد تغييرات المنصة الحساسة", "critical"),
    "office.subscription.view": ("عرض اشتراك المكتب وفواتيره", "normal"),
    "office.subscription.change": ("طلب تغيير باقة المكتب", "sensitive"),
    "platform.subscription.manage": ("إدارة باقات واشتراكات المكاتب", "critical"),
    "platform.subscription.billing": ("تحصيل فواتير اشتراكات المكاتب", "critical"),
    "platform.continuity.manage": ("إدارة الاستمرارية والتعافي", "critical"),
    "platform.release.manage": ("إدارة الإصدارات واختبارات الحمل", "critical"),
    "platform.incident.manage": ("إدارة حوادث المنصة", "critical"),
}

ROLES = {
    "office.owner": (
        "office",
        "مالك المكتب",
        [code for code in PERMISSIONS if code.startswith("office.")],
    ),
    "office.booking_agent": (
        "office",
        "موظف حجوزات",
        ["office.booking.create", "office.boarding.scan"],
    ),
    "office.finance": (
        "office",
        "الموظف المالي",
        [
            "office.payment.confirm_manual",
            "office.finance.view",
            "office.refund.request",
        ],
    ),
    "platform.support": (
        "platform",
        "دعم المنصة",
        [
            "platform.support.manage",
            "platform.dispute.manage",
            "platform.audit.view",
            "platform.office.manage",
            "platform.violation.manage",
            "platform.report.view",
        ],
    ),
    "platform.finance": (
        "platform",
        "مالية المنصة",
        [
            "platform.settlement.manage",
            "platform.settlement.approve",
            "platform.commission.manage",
            "platform.dispute.manage",
            "platform.dispute.finance",
            "platform.report.view",
            "platform.audit.view",
            "platform.subscription.billing",
        ],
    ),
    "platform.compliance": (
        "platform",
        "امتثال المنصة",
        [
            "platform.office.verify",
            "platform.office.manage",
            "platform.violation.manage",
            "platform.risk.view",
            "platform.privacy.manage",
            "platform.audit.view",
            "platform.approval.manage",
        ],
    ),
    "platform.admin": (
        "platform",
        "مدير المنصة",
        [code for code in PERMISSIONS if code.startswith("platform.")],
    ),
}


class Command(BaseCommand):
    help = "Seed immutable foundation roles and permissions"

    @transaction.atomic
    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        permission_objects: dict[str, Permission] = {}
        for code, (name_ar, risk_level) in PERMISSIONS.items():
            permission, _ = Permission.objects.update_or_create(
                code=code,
                defaults={"name_ar": name_ar, "risk_level": risk_level},
            )
            permission_objects[code] = permission

        for code, (scope_type, name_ar, permission_codes) in ROLES.items():
            role, _ = Role.objects.update_or_create(
                code=code,
                defaults={"scope_type": scope_type, "name_ar": name_ar, "is_system": True},
            )
            RolePermission.objects.filter(role=role).delete()
            RolePermission.objects.bulk_create(
                [
                    RolePermission(role=role, permission=permission_objects[permission_code])
                    for permission_code in permission_codes
                ]
            )
        self.stdout.write(self.style.SUCCESS("Foundation roles and permissions seeded"))
