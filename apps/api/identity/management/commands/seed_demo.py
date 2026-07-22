from __future__ import annotations

import hashlib
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import RequestFactory
from django.utils import timezone

from fleet.models import Driver, SeatLayout, SeatLayoutSeat, Vehicle
from geography.models import Location, Route
from identity.models import PlatformRoleAssignment, Role, User
from organizations.models import Office, OfficeBranch, OfficeMembership, TransportOperator
from organizations.services import OfficeContext
from policies.models import PolicyTemplate, PolicyVersion
from subscriptions.models import OfficeSubscription, SubscriptionPlan
from trips.models import Trip
from trips.services import command_trip, create_trip

DEMO_ADMIN_EMAIL = "admin@demo.local"
DEMO_OFFICE_EMAIL = "office@demo.local"
DEMO_AGENT_EMAIL = "agent@demo.local"
DEMO_ADMIN_PASSWORD = "DemoAdmin!2026"  # nosec B105 - documented local demo credential
DEMO_OFFICE_PASSWORD = "DemoOffice!2026"  # nosec B105 - documented local demo credential
DEMO_AGENT_PASSWORD = "DemoAgent!2026"  # nosec B105 - documented local demo credential


class Command(BaseCommand):
    help = "Create or refresh a complete, idempotent local demo environment"

    @transaction.atomic
    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        call_command("seed_foundation", verbosity=0)
        call_command("seed_notification_templates", verbosity=0)

        now = timezone.now()
        admin = self._user(
            email=DEMO_ADMIN_EMAIL,
            full_name="مدير منصة تجريبي",
            password=DEMO_ADMIN_PASSWORD,
            is_platform_staff=True,
        )
        owner = self._user(
            email=DEMO_OFFICE_EMAIL,
            full_name="مالك مكتب الرحلات التجريبي",
            password=DEMO_OFFICE_PASSWORD,
        )
        agent = self._user(
            email=DEMO_AGENT_EMAIL,
            full_name="موظف حجوزات تجريبي",
            password=DEMO_AGENT_PASSWORD,
        )

        platform_role = Role.objects.get(code="platform.admin")
        PlatformRoleAssignment.objects.update_or_create(
            user=admin,
            role=platform_role,
            defaults={"assigned_by": admin, "revoked_at": None},
        )

        operator, _ = TransportOperator.objects.update_or_create(
            registration_number="DEMO-OPERATOR-001",
            defaults={
                "legal_name": "شركة البولمن السورية التجريبية",
                "trade_name": "بولمن الشام",
                "status": "active",
                "country_code": "SY",
                "support_phone": "+963911111111",
            },
        )
        office, _ = Office.objects.update_or_create(
            support_email="office@demo.local",
            defaults={
                "operator": operator,
                "legal_name": "مكتب بولمن الشام التجريبي",
                "trade_name": "مكتب بولمن الشام",
                "office_type": Office.OfficeType.CARRIER,
                "status": Office.Status.ACTIVE,
                "timezone": "Asia/Damascus",
                "default_currency": "SYP",
                "support_phone": "+963922222222",
                "activated_at": now,
            },
        )

        raqqa, _ = Location.objects.update_or_create(
            name_ar="الرقة",
            location_type=Location.LocationType.CITY,
            parent=None,
            defaults={"name_en": "Raqqa", "status": Location.Status.ACTIVE},
        )
        damascus, _ = Location.objects.update_or_create(
            name_ar="دمشق",
            location_type=Location.LocationType.CITY,
            parent=None,
            defaults={"name_en": "Damascus", "status": Location.Status.ACTIVE},
        )
        raqqa_garage, _ = Location.objects.update_or_create(
            name_ar="كراج البولمن الرئيسي - الرقة",
            location_type=Location.LocationType.GARAGE,
            parent=raqqa,
            defaults={
                "name_en": "Raqqa Main Bus Station",
                "address_text": "الرقة - الكراج الرئيسي",
                "status": Location.Status.ACTIVE,
            },
        )
        damascus_garage, _ = Location.objects.update_or_create(
            name_ar="كراج العباسيين - دمشق",
            location_type=Location.LocationType.GARAGE,
            parent=damascus,
            defaults={
                "name_en": "Damascus Abbassiyeen Bus Station",
                "address_text": "دمشق - كراج العباسيين",
                "status": Location.Status.ACTIVE,
            },
        )
        raqqa_branch, _ = OfficeBranch.objects.update_or_create(
            office=office,
            name="فرع الرقة الرئيسي",
            defaults={
                "location": raqqa_garage,
                "phone": "+963933333333",
                "status": "active",
                "is_primary": True,
            },
        )
        damascus_branch, _ = OfficeBranch.objects.update_or_create(
            office=office,
            name="فرع دمشق",
            defaults={
                "location": damascus_garage,
                "phone": "+963944444444",
                "status": "active",
                "is_primary": False,
            },
        )

        owner_role = Role.objects.get(code="office.owner")
        agent_role = Role.objects.get(code="office.booking_agent")
        OfficeMembership.objects.update_or_create(
            user=owner,
            office=office,
            branch=raqqa_branch,
            role=owner_role,
            defaults={"status": OfficeMembership.Status.ACTIVE, "revoked_at": None},
        )
        OfficeMembership.objects.update_or_create(
            user=agent,
            office=office,
            branch=raqqa_branch,
            role=agent_role,
            defaults={"status": OfficeMembership.Status.ACTIVE, "revoked_at": None},
        )

        plan, _ = SubscriptionPlan.objects.update_or_create(
            code="demo-pro",
            defaults={
                "name_ar": "الباقة الاحترافية التجريبية",
                "billing_period": SubscriptionPlan.BillingPeriod.MONTHLY,
                "price_amount": Decimal("0.00"),
                "currency": "SYP",
                "features_json": {
                    "public_booking": True,
                    "reports": True,
                    "offline_boarding": True,
                },
                "limits_json": {
                    "branches": 10,
                    "vehicles": 20,
                    "drivers": 30,
                    "staff": 50,
                    "monthly_trips": 500,
                },
                "status": SubscriptionPlan.Status.ACTIVE,
                "effective_from": now - timedelta(days=30),
                "effective_to": None,
                "version": 1,
                "created_by": admin,
            },
        )
        subscription = OfficeSubscription.objects.filter(
            office=office,
            status__in=OfficeSubscription.ACTIVEISH_STATUSES,
        ).first()
        if subscription is None:
            OfficeSubscription.objects.create(
                office=office,
                plan=plan,
                status=OfficeSubscription.Status.ACTIVE,
                period_start=now - timedelta(days=1),
                period_end=now + timedelta(days=365),
                price_snapshot={"amount": "0.00", "currency": "SYP", "plan_code": plan.code},
                features_snapshot=plan.features_json,
                limits_snapshot=plan.limits_json,
                auto_renew=False,
                source="demo_seed",
            )
        else:
            subscription.plan = plan
            subscription.status = OfficeSubscription.Status.ACTIVE
            subscription.period_start = now - timedelta(days=1)
            subscription.period_end = now + timedelta(days=365)
            subscription.price_snapshot = {"amount": "0.00", "currency": "SYP", "plan_code": plan.code}
            subscription.features_snapshot = plan.features_json
            subscription.limits_snapshot = plan.limits_json
            subscription.save()

        route_out, _ = Route.objects.update_or_create(
            origin_location=raqqa,
            destination_location=damascus,
            defaults={"name_ar": "الرقة ← دمشق", "status": Route.Status.ACTIVE},
        )
        route_back, _ = Route.objects.update_or_create(
            origin_location=damascus,
            destination_location=raqqa,
            defaults={"name_ar": "دمشق ← الرقة", "status": Route.Status.ACTIVE},
        )

        layout, _ = SeatLayout.objects.update_or_create(
            office=office,
            name="بولمان تجريبي 2+2",
            version=1,
            defaults={
                "layout_type": SeatLayout.LayoutType.TWO_PLUS_TWO,
                "seat_count": 32,
                "status": SeatLayout.Status.ACTIVE,
            },
        )
        self._layout_seats(layout)
        vehicle, _ = Vehicle.objects.update_or_create(
            office=office,
            plate_number="RAQ-DEMO-01",
            defaults={
                "operator": operator,
                "fleet_number": "DEMO-01",
                "seat_layout": layout,
                "status": Vehicle.Status.ACTIVE,
                "make_model": "Mercedes Travego",
                "year": 2024,
            },
        )
        driver, _ = Driver.objects.update_or_create(
            operator=operator,
            full_name="أحمد السائق التجريبي",
            defaults={
                "phone": "+963955555555",
                "license_number_ciphertext": b"demo-encrypted-license",
                "license_last4": "2026",
                "license_expires_at": timezone.localdate() + timedelta(days=365),
                "status": Driver.Status.ACTIVE,
            },
        )

        policies = self._policies(now)
        owner_membership = OfficeMembership.objects.get(user=owner, office=office, role=owner_role)
        context = OfficeContext(
            membership=owner_membership,
            permissions=frozenset(owner_role.permissions.values_list("code", flat=True)),
        )
        created_trips: list[Trip] = []
        local_zone = ZoneInfo("Asia/Damascus")
        today_local = timezone.localtime(now, local_zone).date()
        for offset in range(1, 5):
            service_day = today_local + timedelta(days=offset)
            created_trips.append(
                self._ensure_trip(
                    owner=owner,
                    context=context,
                    office=office,
                    branch=raqqa_branch,
                    operator=operator,
                    route=route_out,
                    vehicle=vehicle,
                    driver=driver,
                    policies=policies,
                    departure=timezone.make_aware(datetime.combine(service_day, time(8, 0)), local_zone),
                    arrival=timezone.make_aware(datetime.combine(service_day, time(14, 0)), local_zone),
                    price=Decimal("125000.00"),
                )
            )
            created_trips.append(
                self._ensure_trip(
                    owner=owner,
                    context=context,
                    office=office,
                    branch=damascus_branch,
                    operator=operator,
                    route=route_back,
                    vehicle=vehicle,
                    driver=driver,
                    policies=policies,
                    departure=timezone.make_aware(datetime.combine(service_day, time(17, 0)), local_zone),
                    arrival=timezone.make_aware(datetime.combine(service_day, time(23, 0)), local_zone),
                    price=Decimal("125000.00"),
                )
            )

        self.stdout.write(self.style.SUCCESS("Demo environment is ready"))
        self.stdout.write(f"Platform admin: {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
        self.stdout.write(f"Office owner:   {DEMO_OFFICE_EMAIL} / {DEMO_OFFICE_PASSWORD}")
        self.stdout.write(f"Booking agent:  {DEMO_AGENT_EMAIL} / {DEMO_AGENT_PASSWORD}")
        self.stdout.write(f"Office ID:      {office.public_id}")
        self.stdout.write(f"Demo trips:     {len(created_trips)} bookable trips")

    def _user(self, *, email: str, full_name: str, password: str, is_platform_staff: bool = False) -> User:
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "full_name": full_name,
                "status": User.Status.ACTIVE,
                "is_platform_staff": is_platform_staff,
                "email_verified_at": timezone.now(),
            },
        )
        user.full_name = full_name
        user.status = User.Status.ACTIVE
        user.is_platform_staff = is_platform_staff
        user.email_verified_at = user.email_verified_at or timezone.now()
        user.set_password(password)
        user.save()
        return user

    def _layout_seats(self, layout: SeatLayout) -> None:
        columns = ("A", "B", "C", "D")
        for row in range(1, 9):
            for column_no, suffix in enumerate(columns, start=1):
                code = f"{row}{suffix}"
                SeatLayoutSeat.objects.update_or_create(
                    layout=layout,
                    seat_code=code,
                    defaults={
                        "row_no": row,
                        "column_no": column_no,
                        "seat_type": SeatLayoutSeat.SeatType.STANDARD,
                        "is_sellable": True,
                        "metadata": {"side": "right" if column_no <= 2 else "left"},
                    },
                )

    def _policies(self, now: datetime) -> list[PolicyVersion]:
        definitions: dict[str, tuple[str, str, dict[str, object]]] = {
            "cancellation": (
                "سياسة الإلغاء التجريبية",
                "يمكن إلغاء الحجز قبل موعد الانطلاق وفق الخصم الموضح في شاشة الإدارة.",
                {"summary": "إلغاء مرن قبل الانطلاق مع احتساب الرسوم.", "refund_percent": 90},
            ),
            "payment": (
                "سياسة الدفع التجريبية",
                "يمكن الدفع نقدًا في المكتب أو عبر تحويل يدوي خلال المهلة المحددة.",
                {"summary": "الدفع في المكتب أو بتحويل يدوي.", "payment_deadline_minutes": 120},
            ),
            "boarding": (
                "سياسة الصعود التجريبية",
                "يفتح الصعود قبل ساعة ويغلق قبل خمس عشرة دقيقة من الانطلاق.",
                {"summary": "الحضور قبل الانطلاق بساعة مع إبراز التذكرة."},
            ),
        }
        versions: list[PolicyVersion] = []
        for policy_type, (title, content, rules) in definitions.items():
            template, _ = PolicyTemplate.objects.update_or_create(
                code=f"demo.{policy_type}",
                defaults={
                    "policy_type": policy_type,
                    "owner_scope": PolicyTemplate.OwnerScope.PLATFORM,
                    "status": PolicyTemplate.Status.ACTIVE,
                },
            )
            version, _ = PolicyVersion.objects.update_or_create(
                template=template,
                office=None,
                version_no=1,
                language="ar",
                defaults={
                    "title": title,
                    "content_markdown": content,
                    "rules_json": rules,
                    "effective_from": now - timedelta(days=30),
                    "effective_to": None,
                    "published_at": now - timedelta(days=30),
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                },
            )
            versions.append(version)
        return versions

    def _ensure_trip(
        self,
        *,
        owner: User,
        context: OfficeContext,
        office: Office,
        branch: OfficeBranch,
        operator: TransportOperator,
        route: Route,
        vehicle: Vehicle,
        driver: Driver,
        policies: list[PolicyVersion],
        departure: datetime,
        arrival: datetime,
        price: Decimal,
    ) -> Trip:
        existing = Trip.objects.filter(
            office=office,
            route=route,
            scheduled_departure_at=departure,
        ).first()
        if existing is not None:
            return existing
        request = RequestFactory().post(
            "/v1/office/trips",
            HTTP_IDEMPOTENCY_KEY=f"demo-trip-{route.public_id}-{departure.date().isoformat()}",
            REMOTE_ADDR="127.0.0.1",
        )
        request.user = owner
        trip = create_trip(
            context=context,
            actor=owner,
            request=request,
            data={
                "route_id": route.public_id,
                "branch_id": branch.public_id,
                "operator_id": operator.public_id,
                "vehicle_id": vehicle.public_id,
                "driver_id": driver.public_id,
                "scheduled_departure_at": departure,
                "scheduled_arrival_at": arrival,
                "currency": "SYP",
                "base_price": price,
                "policy_version_ids": [policy.id for policy in policies],
                "payment_methods": ["office_cash", "manual_transfer"],
                "booking_open_at": timezone.now() - timedelta(days=1),
                "booking_close_at": departure - timedelta(hours=2),
                "boarding_open_at": departure - timedelta(hours=1),
                "boarding_close_at": departure - timedelta(minutes=15),
            },
        )
        trip = command_trip(
            context=context,
            actor=owner,
            request=request,
            trip_id=trip.public_id,
            data={"command": "schedule", "version": trip.version},
        )
        trip.pricing_snapshot = {
            **trip.pricing_snapshot,
            "fee_per_passenger": "5000.00",
            "fixed_fee": "0.00",
        }
        trip.save(update_fields=["pricing_snapshot"])
        trip = command_trip(
            context=context,
            actor=owner,
            request=request,
            trip_id=trip.public_id,
            data={"command": "publish", "version": trip.version},
        )
        return command_trip(
            context=context,
            actor=owner,
            request=request,
            trip_id=trip.public_id,
            data={"command": "open_booking", "version": trip.version},
        )
