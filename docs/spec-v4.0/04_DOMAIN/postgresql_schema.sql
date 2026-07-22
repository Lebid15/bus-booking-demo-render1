-- PostgreSQL 18 normative baseline DDL
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- الحسابات البشرية العامة
CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    email citext,
    phone_e164 varchar(20),
    password_hash text,
    full_name varchar(160) NOT NULL,
    preferred_language varchar(5) NOT NULL DEFAULT 'ar',
    status varchar(24) NOT NULL DEFAULT 'active',
    is_platform_staff boolean NOT NULL DEFAULT false,
    email_verified_at timestamptz,
    phone_verified_at timestamptz,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (email IS NOT NULL OR phone_e164 IS NOT NULL)
);

-- ملف الزبون الاختياري
CREATE TABLE customer_profiles (
    user_id uuid PRIMARY KEY,
    date_of_birth date,
    gender varchar(12),
    nationality_code char(2),
    marketing_consent boolean NOT NULL DEFAULT false,
    deleted_at timestamptz,
    CHECK (gender IS NULL OR gender IN ('male','female'))
);

-- الجلسات
CREATE TABLE user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    token_hash bytea NOT NULL UNIQUE,
    device_id uuid,
    ip_hash bytea,
    user_agent text,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at)
);

-- الأجهزة الموثوقة
CREATE TABLE user_devices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    device_fingerprint_hash bytea NOT NULL,
    label varchar(120),
    trusted_at timestamptz,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    UNIQUE(user_id, device_fingerprint_hash)
);

-- وسائل MFA
CREATE TABLE mfa_methods (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    method_type varchar(20) NOT NULL,
    secret_ciphertext bytea,
    credential_id bytea,
    is_primary boolean NOT NULL DEFAULT false,
    verified_at timestamptz,
    disabled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (method_type IN ('totp','webauthn','recovery'))
);

-- الأدوار المعرفة
CREATE TABLE roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(80) NOT NULL UNIQUE,
    scope_type varchar(20) NOT NULL,
    name_ar varchar(120) NOT NULL,
    is_system boolean NOT NULL DEFAULT true,
    CHECK (scope_type IN ('platform','office','branch'))
);

-- الصلاحيات الذرية
CREATE TABLE permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(120) NOT NULL UNIQUE,
    name_ar varchar(160) NOT NULL,
    risk_level varchar(12) NOT NULL DEFAULT 'normal',
    CHECK (risk_level IN ('normal','sensitive','critical'))
);

-- ربط الدور بالصلاحيات
CREATE TABLE role_permissions (
    role_id uuid,
    permission_id uuid,
    PRIMARY KEY (role_id, permission_id)
);

-- الناقل الفعلي/الشركة
CREATE TABLE transport_operators (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    legal_name varchar(200) NOT NULL,
    trade_name varchar(160),
    registration_number varchar(100),
    status varchar(24) NOT NULL DEFAULT 'draft',
    country_code char(2) NOT NULL DEFAULT 'SY',
    support_phone varchar(20),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- المكتب البائع المتعاقد
CREATE TABLE offices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    operator_id uuid,
    legal_name varchar(200) NOT NULL,
    trade_name varchar(160) NOT NULL,
    office_type varchar(24) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'draft',
    timezone varchar(64) NOT NULL DEFAULT 'Asia/Damascus',
    default_currency char(3) NOT NULL DEFAULT 'SYP',
    support_phone varchar(20) NOT NULL,
    support_email citext,
    commission_profile_id uuid,
    activated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (office_type IN ('carrier','branch','authorized_agent','garage_office'))
);

-- فروع المكتب ونقاط التشغيل
CREATE TABLE office_branches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid NOT NULL,
    public_id varchar(26) NOT NULL UNIQUE,
    name varchar(160) NOT NULL,
    location_id uuid NOT NULL,
    phone varchar(20),
    status varchar(20) NOT NULL DEFAULT 'active',
    is_primary boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(office_id, name)
);

-- عضوية موظف في مكتب/فرع
CREATE TABLE office_memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    office_id uuid NOT NULL,
    branch_id uuid,
    role_id uuid NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active',
    can_approve_own_actions boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    UNIQUE(user_id, office_id, branch_id, role_id)
);

-- ملف تحقق المكتب
CREATE TABLE verification_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'draft',
    risk_level varchar(12) NOT NULL DEFAULT 'basic',
    submitted_at timestamptz,
    decided_at timestamptz,
    reviewer_user_id uuid,
    decision_reason text,
    version integer NOT NULL DEFAULT 1,
    UNIQUE(office_id, version)
);

-- وثائق المكتب/الناقل
CREATE TABLE office_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid NOT NULL,
    verification_case_id uuid,
    document_type varchar(64) NOT NULL,
    storage_object_key text NOT NULL,
    sha256 char(64) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'pending',
    issued_at date,
    expires_at date,
    reviewed_by uuid,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(office_id, document_type, sha256)
);

-- حسابات تسوية المكتب
CREATE TABLE office_payout_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid NOT NULL,
    method_type varchar(30) NOT NULL,
    account_holder_name varchar(200) NOT NULL,
    account_reference_ciphertext bytea NOT NULL,
    account_reference_last4 varchar(8),
    status varchar(24) NOT NULL DEFAULT 'pending',
    verified_at timestamptz,
    effective_at timestamptz,
    created_by uuid NOT NULL,
    approved_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (approved_by IS NULL OR approved_by <> created_by)
);

-- المدن والكراجات والنقاط
CREATE TABLE locations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    location_type varchar(20) NOT NULL,
    parent_id uuid,
    name_ar varchar(160) NOT NULL,
    name_en varchar(160),
    address_text text,
    latitude numeric(9,6),
    longitude numeric(9,6),
    status varchar(20) NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (location_type IN ('city','garage','boarding_point','dropoff_point')),
    CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

-- الخط التجاري
CREATE TABLE routes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    origin_location_id uuid NOT NULL,
    destination_location_id uuid NOT NULL,
    name_ar varchar(200) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (origin_location_id <> destination_location_id),
    UNIQUE(origin_location_id,destination_location_id)
);

-- النقاط الافتراضية لمسار
CREATE TABLE route_stops (
    route_id uuid,
    sequence_no smallint NOT NULL,
    location_id uuid NOT NULL,
    stop_type varchar(20) NOT NULL,
    offset_minutes integer NOT NULL DEFAULT 0,
    PRIMARY KEY (route_id, sequence_no),
    CHECK(sequence_no>0),
    UNIQUE(route_id,location_id)
);

-- قالب مخطط البولمان
CREATE TABLE seat_layouts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid NOT NULL,
    name varchar(160) NOT NULL,
    layout_type varchar(20) NOT NULL,
    seat_count smallint NOT NULL,
    version integer NOT NULL DEFAULT 1,
    status varchar(20) NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK(seat_count>0),
    UNIQUE(office_id,name,version)
);

-- مقاعد المخطط
CREATE TABLE seat_layout_seats (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    layout_id uuid NOT NULL,
    seat_code varchar(12) NOT NULL,
    row_no smallint NOT NULL,
    column_no smallint NOT NULL,
    seat_type varchar(20) NOT NULL DEFAULT 'standard',
    is_sellable boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(layout_id,seat_code),
    UNIQUE(layout_id,row_no,column_no),
    CHECK(row_no>0 AND column_no>0)
);

-- تعريف المجاورة المنطقي
CREATE TABLE seat_adjacencies (
    layout_id uuid,
    seat_a_id uuid,
    seat_b_id uuid,
    adjacency_type varchar(20) NOT NULL DEFAULT 'same_unit',
    PRIMARY KEY (layout_id, seat_a_id, seat_b_id),
    CHECK(seat_a_id < seat_b_id)
);

-- البولمانات
CREATE TABLE vehicles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid NOT NULL,
    operator_id uuid,
    public_id varchar(26) NOT NULL UNIQUE,
    plate_number varchar(40) NOT NULL,
    fleet_number varchar(40),
    seat_layout_id uuid NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active',
    make_model varchar(160),
    year smallint,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(office_id,plate_number),
    CHECK(year IS NULL OR year BETWEEN 1980 AND 2100)
);

-- السائقون
CREATE TABLE drivers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id uuid NOT NULL,
    full_name varchar(160) NOT NULL,
    phone varchar(20),
    license_number_ciphertext bytea NOT NULL,
    license_last4 varchar(8),
    license_expires_at date,
    status varchar(20) NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- قوالب السياسات
CREATE TABLE policy_templates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(80) NOT NULL UNIQUE,
    policy_type varchar(40) NOT NULL,
    owner_scope varchar(20) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active'
);

-- إصدارات السياسات
CREATE TABLE policy_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id uuid NOT NULL,
    office_id uuid,
    version_no integer NOT NULL,
    language varchar(5) NOT NULL DEFAULT 'ar',
    title varchar(200) NOT NULL,
    content_markdown text NOT NULL,
    rules_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    published_at timestamptz,
    content_sha256 char(64) NOT NULL,
    UNIQUE(template_id,office_id,version_no,language),
    CHECK(effective_to IS NULL OR effective_to>effective_from)
);

-- الموافقات على السياسات
CREATE TABLE policy_acceptances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_version_id uuid NOT NULL,
    subject_type varchar(20) NOT NULL,
    subject_id uuid NOT NULL,
    accepted_by_user_id uuid,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    ip_hash bytea,
    user_agent_hash bytea,
    UNIQUE(policy_version_id,subject_type,subject_id)
);

-- إعدادات قابلة للتغيير
CREATE TABLE configuration_values (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_type varchar(20) NOT NULL,
    scope_id uuid,
    key varchar(120) NOT NULL,
    value_json jsonb NOT NULL,
    value_type varchar(20) NOT NULL,
    effective_from timestamptz NOT NULL DEFAULT now(),
    effective_to timestamptz,
    created_by uuid NOT NULL,
    approved_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(scope_type,scope_id,key,effective_from),
    CHECK(effective_to IS NULL OR effective_to>effective_from)
);

-- نسخة تشغيلية لرحلة
CREATE TABLE trips (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    office_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    operator_id uuid NOT NULL,
    route_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    seat_layout_id uuid NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'draft',
    scheduled_departure_at timestamptz NOT NULL,
    scheduled_arrival_at timestamptz,
    actual_departure_at timestamptz,
    actual_arrival_at timestamptz,
    currency char(3) NOT NULL,
    base_price numeric(18,2) NOT NULL,
    booking_open_at timestamptz,
    booking_close_at timestamptz,
    boarding_open_at timestamptz,
    boarding_close_at timestamptz,
    policy_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    pricing_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    version integer NOT NULL DEFAULT 1,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK(scheduled_arrival_at IS NULL OR scheduled_arrival_at>scheduled_departure_at),
    CHECK(base_price>=0),
    CHECK(booking_close_at IS NULL OR booking_close_at<=scheduled_departure_at)
);

-- نقاط الرحلة الفعلية
CREATE TABLE trip_stops (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL,
    sequence_no smallint NOT NULL,
    location_id uuid NOT NULL,
    scheduled_at timestamptz,
    actual_at timestamptz,
    stop_type varchar(20) NOT NULL,
    UNIQUE(trip_id,sequence_no),
    UNIQUE(trip_id,location_id),
    CHECK(sequence_no>0)
);

-- مخزون المقاعد لكل رحلة
CREATE TABLE trip_seats (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL,
    layout_seat_id uuid NOT NULL,
    seat_code varchar(12) NOT NULL,
    seat_type varchar(20) NOT NULL,
    sellable boolean NOT NULL DEFAULT true,
    blocked_reason varchar(160),
    version integer NOT NULL DEFAULT 1,
    UNIQUE(trip_id,layout_seat_id),
    UNIQUE(trip_id,seat_code)
);

-- حجز مؤقت للمقعد
CREATE TABLE seat_holds (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL,
    trip_seat_id uuid NOT NULL,
    hold_token_hash bytea NOT NULL UNIQUE,
    owner_session_id uuid,
    owner_booking_draft_id uuid,
    status varchar(16) NOT NULL DEFAULT 'active',
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    CHECK(expires_at>created_at)
);

-- الحجز الرئيسي
CREATE TABLE bookings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    pnr varchar(12) NOT NULL UNIQUE,
    office_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    trip_id uuid NOT NULL,
    customer_user_id uuid,
    source varchar(24) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'draft',
    payment_status varchar(24) NOT NULL DEFAULT 'unpaid',
    contact_name varchar(160) NOT NULL,
    contact_phone varchar(20) NOT NULL,
    contact_email citext,
    currency char(3) NOT NULL,
    subtotal_amount numeric(18,2) NOT NULL,
    discount_amount numeric(18,2) NOT NULL DEFAULT 0,
    fee_amount numeric(18,2) NOT NULL DEFAULT 0,
    total_amount numeric(18,2) NOT NULL,
    paid_amount numeric(18,2) NOT NULL DEFAULT 0,
    refunded_amount numeric(18,2) NOT NULL DEFAULT 0,
    payment_deadline_at timestamptz,
    policy_snapshot jsonb NOT NULL,
    pricing_snapshot jsonb NOT NULL,
    commission_snapshot jsonb NOT NULL,
    terms_version_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
    manage_token_hash bytea NOT NULL UNIQUE,
    version integer NOT NULL DEFAULT 1,
    confirmed_at timestamptz,
    cancelled_at timestamptz,
    created_by_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK(subtotal_amount>=0 AND discount_amount>=0 AND fee_amount>=0 AND total_amount>=0),
    CHECK(total_amount=subtotal_amount-discount_amount+fee_amount),
    CHECK(paid_amount>=0 AND refunded_amount>=0 AND refunded_amount<=paid_amount)
);

-- ركاب الحجز
CREATE TABLE booking_passengers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    sequence_no smallint NOT NULL,
    full_name varchar(160) NOT NULL,
    gender varchar(12) NOT NULL,
    passenger_type varchar(16) NOT NULL DEFAULT 'adult',
    date_of_birth date,
    nationality_code char(2),
    identity_type varchar(24),
    identity_number_normalized varchar(80),
    boarding_status varchar(28) NOT NULL DEFAULT 'not_arrived',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(booking_id,sequence_no),
    CHECK(gender IN ('male','female')),
    CHECK(passenger_type IN ('adult','child','infant'))
);

-- تخصيص المقعد النهائي
CREATE TABLE seat_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL,
    booking_id uuid NOT NULL,
    passenger_id uuid NOT NULL,
    trip_seat_id uuid NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active',
    price_amount numeric(18,2) NOT NULL,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    superseded_by_id uuid,
    CHECK(price_amount>=0)
);

-- إصدارات التذاكر
CREATE TABLE tickets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    passenger_id uuid NOT NULL,
    seat_assignment_id uuid NOT NULL,
    version_no integer NOT NULL DEFAULT 1,
    status varchar(20) NOT NULL DEFAULT 'active',
    qr_token_hash bytea NOT NULL UNIQUE,
    qr_payload_signature bytea NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    used_at timestamptz,
    UNIQUE(passenger_id,version_no)
);

-- أحداث الصعود غير القابلة للتعديل
CREATE TABLE boarding_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL,
    passenger_id uuid NOT NULL,
    ticket_id uuid,
    event_type varchar(24) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_user_id uuid,
    device_id uuid,
    offline_event_id varchar(80),
    reason_code varchar(80),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- إصدارات قائمة الركاب
CREATE TABLE trip_manifests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL,
    version_no integer NOT NULL,
    status varchar(20) NOT NULL,
    manifest_json jsonb NOT NULL,
    sha256 char(64) NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    generated_by uuid,
    UNIQUE(trip_id,version_no)
);

-- نية دفع
CREATE TABLE payment_intents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    method_type varchar(30) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'created',
    amount numeric(18,2) NOT NULL,
    currency char(3) NOT NULL,
    provider_code varchar(60),
    provider_reference varchar(160),
    idempotency_key varchar(120) NOT NULL,
    expires_at timestamptz,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(booking_id,idempotency_key),
    CHECK(amount>0)
);

-- الحركات المالية الخارجية/النقدية
CREATE TABLE payment_transactions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_intent_id uuid NOT NULL,
    transaction_type varchar(20) NOT NULL,
    status varchar(20) NOT NULL,
    amount numeric(18,2) NOT NULL,
    currency char(3) NOT NULL,
    provider_event_id varchar(160),
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    raw_reference_hash bytea,
    CHECK(amount>0)
);

-- إثبات التحويل اليدوي
CREATE TABLE manual_payment_submissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_intent_id uuid NOT NULL,
    sender_reference varchar(160),
    transfer_reference varchar(160) NOT NULL,
    transferred_at timestamptz NOT NULL,
    amount numeric(18,2) NOT NULL,
    proof_object_key text,
    proof_sha256 char(64),
    status varchar(20) NOT NULL DEFAULT 'submitted',
    submitted_at timestamptz NOT NULL DEFAULT now(),
    reviewed_by uuid,
    reviewed_at timestamptz,
    rejection_reason text,
    UNIQUE(transfer_reference),
    CHECK(amount>0)
);

-- طلبات ونتائج الاسترداد
CREATE TABLE refunds (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    payment_intent_id uuid,
    status varchar(24) NOT NULL DEFAULT 'requested',
    reason_code varchar(80) NOT NULL,
    requested_amount numeric(18,2) NOT NULL,
    approved_amount numeric(18,2),
    currency char(3) NOT NULL,
    requested_by uuid,
    approved_by uuid,
    provider_reference varchar(160),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK(requested_amount>0),
    CHECK(approved_amount IS NULL OR approved_amount BETWEEN 0 AND requested_amount),
    CHECK(approved_by IS NULL OR approved_by<>requested_by)
);

-- نزاع داخلي
CREATE TABLE disputes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'open',
    category varchar(60) NOT NULL,
    disputed_amount numeric(18,2),
    opened_by_type varchar(20) NOT NULL,
    opened_by_id uuid,
    assigned_to uuid,
    decision_code varchar(80),
    decision_summary text,
    opened_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    closed_at timestamptz,
    CHECK(disputed_amount IS NULL OR disputed_amount>=0)
);

-- اعتراض مزود الدفع
CREATE TABLE chargebacks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_transaction_id uuid NOT NULL,
    provider_case_id varchar(160) NOT NULL UNIQUE,
    status varchar(24) NOT NULL,
    amount numeric(18,2) NOT NULL,
    currency char(3) NOT NULL,
    deadline_at timestamptz,
    opened_at timestamptz NOT NULL,
    closed_at timestamptz,
    CHECK(amount>0)
);

-- دليل حسابات داخلي
CREATE TABLE ledger_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid,
    code varchar(80) NOT NULL,
    account_type varchar(20) NOT NULL,
    currency char(3) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(office_id,code,currency)
);

-- رأس القيد المحاسبي
CREATE TABLE ledger_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type varchar(80) NOT NULL,
    event_id uuid NOT NULL,
    booking_id uuid,
    trip_id uuid,
    office_id uuid,
    currency char(3) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'posted',
    occurred_at timestamptz NOT NULL,
    posted_at timestamptz NOT NULL DEFAULT now(),
    reversal_of_id uuid,
    description text,
    UNIQUE(event_type,event_id,currency),
    CHECK(reversal_of_id IS NULL OR status='reversed')
);

-- طرفا القيد
CREATE TABLE ledger_postings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id uuid NOT NULL,
    account_id uuid NOT NULL,
    direction char(1) NOT NULL,
    amount numeric(18,2) NOT NULL,
    memo varchar(240),
    CHECK(direction IN ('D','C')),
    CHECK(amount>0)
);

-- استحقاق عمولة الحجز
CREATE TABLE commissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id uuid NOT NULL,
    office_id uuid NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'expected',
    basis_amount numeric(18,2) NOT NULL,
    rate numeric(9,6) NOT NULL,
    fixed_amount numeric(18,2) NOT NULL DEFAULT 0,
    commission_amount numeric(18,2) NOT NULL,
    currency char(3) NOT NULL,
    earned_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(booking_id),
    CHECK(basis_amount>=0 AND rate>=0 AND fixed_amount>=0 AND commission_amount>=0)
);

-- دفعة تسوية لمكتب
CREATE TABLE settlements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    office_id uuid NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    currency char(3) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'draft',
    gross_amount numeric(18,2) NOT NULL DEFAULT 0,
    commission_amount numeric(18,2) NOT NULL DEFAULT 0,
    refund_amount numeric(18,2) NOT NULL DEFAULT 0,
    reserve_amount numeric(18,2) NOT NULL DEFAULT 0,
    adjustment_amount numeric(18,2) NOT NULL DEFAULT 0,
    net_amount numeric(18,2) NOT NULL DEFAULT 0,
    created_by uuid NOT NULL,
    approved_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    paid_at timestamptz,
    UNIQUE(office_id,period_start,period_end,currency),
    CHECK(period_end>=period_start),
    CHECK(approved_by IS NULL OR approved_by<>created_by)
);

-- تفاصيل التسوية
CREATE TABLE settlement_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    settlement_id uuid NOT NULL,
    item_type varchar(40) NOT NULL,
    source_type varchar(40) NOT NULL,
    source_id uuid NOT NULL,
    amount numeric(18,2) NOT NULL,
    description varchar(240),
    UNIQUE(settlement_id,item_type,source_type,source_id)
);

-- حالات الدعم
CREATE TABLE support_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    booking_id uuid,
    trip_id uuid,
    office_id uuid,
    opened_by_user_id uuid,
    priority varchar(8) NOT NULL DEFAULT 'P3',
    category varchar(60) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'open',
    owner_user_id uuid,
    sla_due_at timestamptz,
    resolution_code varchar(80),
    opened_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    closed_at timestamptz,
    CHECK(priority IN ('P0','P1','P2','P3','P4'))
);

-- رسائل الحالة
CREATE TABLE support_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL,
    sender_type varchar(20) NOT NULL,
    sender_user_id uuid,
    body text NOT NULL,
    visibility varchar(20) NOT NULL DEFAULT 'shared',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- الإشعار المنطقي
CREATE TABLE notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type varchar(80) NOT NULL,
    recipient_type varchar(20) NOT NULL,
    recipient_id uuid,
    booking_id uuid,
    template_code varchar(80) NOT NULL,
    language varchar(5) NOT NULL DEFAULT 'ar',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status varchar(20) NOT NULL DEFAULT 'queued',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- محاولات القنوات
CREATE TABLE notification_deliveries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id uuid NOT NULL,
    channel varchar(20) NOT NULL,
    destination_hash bytea,
    provider_message_id varchar(160),
    status varchar(20) NOT NULL DEFAULT 'queued',
    attempt_no smallint NOT NULL DEFAULT 1,
    next_attempt_at timestamptz,
    sent_at timestamptz,
    delivered_at timestamptz,
    error_code varchar(80),
    UNIQUE(notification_id,channel,attempt_no)
);

-- تقييم خطر
CREATE TABLE risk_assessments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type varchar(30) NOT NULL,
    subject_id uuid NOT NULL,
    score numeric(6,3) NOT NULL,
    decision varchar(24) NOT NULL,
    model_version varchar(40) NOT NULL,
    signals jsonb NOT NULL DEFAULT '{}'::jsonb,
    review_status varchar(20),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK(score BETWEEN 0 AND 100)
);

-- سجل التدقيق
CREATE TABLE audit_logs (
    id bigserial,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_user_id uuid,
    actor_type varchar(20) NOT NULL,
    office_id uuid,
    action varchar(120) NOT NULL,
    object_type varchar(80) NOT NULL,
    object_id uuid,
    request_id uuid,
    ip_hash bytea,
    before_json jsonb,
    after_json jsonb,
    reason_code varchar(80),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- منع تكرار أوامر API
CREATE TABLE idempotency_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_type varchar(30) NOT NULL,
    scope_id uuid,
    key varchar(120) NOT NULL,
    request_hash char(64) NOT NULL,
    response_status integer,
    response_body jsonb,
    locked_until timestamptz,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(scope_type,scope_id,key)
);

-- Transactional outbox
CREATE TABLE outbox_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type varchar(80) NOT NULL,
    aggregate_id uuid NOT NULL,
    event_type varchar(120) NOT NULL,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz
);

-- أحداث مزودي الدفع
CREATE TABLE webhook_deliveries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_code varchar(60) NOT NULL,
    provider_event_id varchar(160) NOT NULL,
    event_type varchar(120) NOT NULL,
    signature_valid boolean NOT NULL,
    payload_hash char(64) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'received',
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    error_code varchar(80),
    UNIQUE(provider_code,provider_event_id)
);

-- طلبات الخصوصية
CREATE TABLE data_subject_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid,
    contact_phone varchar(20),
    request_type varchar(24) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'submitted',
    submitted_at timestamptz NOT NULL DEFAULT now(),
    due_at timestamptz,
    completed_at timestamptz,
    decision_reason text
);

-- الحجز القانوني
CREATE TABLE legal_holds (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type varchar(40) NOT NULL,
    subject_id uuid NOT NULL,
    reason text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    placed_by uuid NOT NULL,
    placed_at timestamptz NOT NULL DEFAULT now(),
    released_by uuid,
    released_at timestamptz
);

-- ملفات العمولة القابلة للإصدار
CREATE TABLE commission_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(80) NOT NULL UNIQUE,
    name_ar varchar(160) NOT NULL,
    calculation_type varchar(20) NOT NULL,
    percentage_rate numeric(9,6) NOT NULL DEFAULT 0,
    fixed_amount numeric(18,2) NOT NULL DEFAULT 0,
    currency char(3),
    status varchar(20) NOT NULL DEFAULT 'active',
    effective_from timestamptz NOT NULL DEFAULT now(),
    effective_to timestamptz,
    created_by uuid NOT NULL,
    CHECK(percentage_rate>=0 AND fixed_amount>=0),
    CHECK(effective_to IS NULL OR effective_to>effective_from)
);

-- باقات اشتراك المكاتب
CREATE TABLE subscription_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(80) NOT NULL UNIQUE,
    name_ar varchar(160) NOT NULL,
    billing_period varchar(20) NOT NULL,
    price_amount numeric(18,2) NOT NULL,
    currency char(3) NOT NULL,
    features_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    limits_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    status varchar(20) NOT NULL DEFAULT 'active',
    effective_from timestamptz NOT NULL DEFAULT now(),
    effective_to timestamptz,
    CHECK(price_amount>=0),
    CHECK(effective_to IS NULL OR effective_to>effective_from)
);

-- اشتراك مكتب في باقة
CREATE TABLE office_subscriptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'active',
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    price_snapshot jsonb NOT NULL,
    features_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    auto_renew boolean NOT NULL DEFAULT false,
    cancel_at_period_end boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK(period_end>period_start)
);

-- فواتير اشتراك المكتب
CREATE TABLE subscription_invoices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id varchar(26) NOT NULL UNIQUE,
    office_subscription_id uuid NOT NULL,
    office_id uuid NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'open',
    currency char(3) NOT NULL,
    subtotal_amount numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL DEFAULT 0,
    total_amount numeric(18,2) NOT NULL,
    due_at timestamptz NOT NULL,
    paid_at timestamptz,
    ledger_entry_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK(subtotal_amount>=0 AND tax_amount>=0 AND total_amount=subtotal_amount+tax_amount)
);

-- سجل الملفات الخاصة
CREATE TABLE stored_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_scope varchar(30) NOT NULL,
    owner_id uuid,
    purpose varchar(60) NOT NULL,
    object_key text NOT NULL UNIQUE,
    original_filename varchar(255),
    mime_type varchar(120) NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 char(64) NOT NULL,
    scan_status varchar(20) NOT NULL DEFAULT 'pending',
    retention_until timestamptz,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CHECK(size_bytes>0),
    UNIQUE(owner_scope,owner_id,purpose,sha256)
);

-- مرفقات حالات الدعم
CREATE TABLE support_attachments (
    case_id uuid,
    file_id uuid,
    uploaded_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, file_id)
);

-- حوادث وتوقفات الرحلات
CREATE TABLE trip_incidents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL,
    severity varchar(12) NOT NULL,
    incident_type varchar(60) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'open',
    description text NOT NULL,
    occurred_at timestamptz NOT NULL,
    opened_by uuid,
    resolved_at timestamptz,
    resolution_summary text,
    CHECK(severity IN ('SEV1','SEV2','SEV3'))
);

-- مخالفات المكتب
CREATE TABLE office_violations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office_id uuid NOT NULL,
    booking_id uuid,
    trip_id uuid,
    severity varchar(16) NOT NULL,
    code varchar(80) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'open',
    description text NOT NULL,
    financial_penalty numeric(18,2),
    currency char(3),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    CHECK(financial_penalty IS NULL OR financial_penalty>=0)
);

ALTER TABLE customer_profiles ADD CONSTRAINT fk_customer_profiles_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE user_sessions ADD CONSTRAINT fk_user_sessions_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE user_sessions ADD CONSTRAINT fk_user_sessions_device_id FOREIGN KEY (device_id) REFERENCES user_devices(id) ON DELETE RESTRICT;
ALTER TABLE user_devices ADD CONSTRAINT fk_user_devices_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE mfa_methods ADD CONSTRAINT fk_mfa_methods_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE role_permissions ADD CONSTRAINT fk_role_permissions_role_id FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT;
ALTER TABLE role_permissions ADD CONSTRAINT fk_role_permissions_permission_id FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE RESTRICT;
ALTER TABLE offices ADD CONSTRAINT fk_offices_operator_id FOREIGN KEY (operator_id) REFERENCES transport_operators(id) ON DELETE RESTRICT;
ALTER TABLE offices ADD CONSTRAINT fk_offices_commission_profile_id FOREIGN KEY (commission_profile_id) REFERENCES commission_profiles(id) ON DELETE RESTRICT;
ALTER TABLE office_branches ADD CONSTRAINT fk_office_branches_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE office_branches ADD CONSTRAINT fk_office_branches_location_id FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE RESTRICT;
ALTER TABLE office_memberships ADD CONSTRAINT fk_office_memberships_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE office_memberships ADD CONSTRAINT fk_office_memberships_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE office_memberships ADD CONSTRAINT fk_office_memberships_branch_id FOREIGN KEY (branch_id) REFERENCES office_branches(id) ON DELETE RESTRICT;
ALTER TABLE office_memberships ADD CONSTRAINT fk_office_memberships_role_id FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT;
ALTER TABLE verification_cases ADD CONSTRAINT fk_verification_cases_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE verification_cases ADD CONSTRAINT fk_verification_cases_reviewer_user_id FOREIGN KEY (reviewer_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE office_documents ADD CONSTRAINT fk_office_documents_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE office_documents ADD CONSTRAINT fk_office_documents_verification_case_id FOREIGN KEY (verification_case_id) REFERENCES verification_cases(id) ON DELETE RESTRICT;
ALTER TABLE office_documents ADD CONSTRAINT fk_office_documents_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE office_payout_accounts ADD CONSTRAINT fk_office_payout_accounts_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE office_payout_accounts ADD CONSTRAINT fk_office_payout_accounts_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE office_payout_accounts ADD CONSTRAINT fk_office_payout_accounts_approved_by FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE locations ADD CONSTRAINT fk_locations_parent_id FOREIGN KEY (parent_id) REFERENCES locations(id) ON DELETE RESTRICT;
ALTER TABLE routes ADD CONSTRAINT fk_routes_origin_location_id FOREIGN KEY (origin_location_id) REFERENCES locations(id) ON DELETE RESTRICT;
ALTER TABLE routes ADD CONSTRAINT fk_routes_destination_location_id FOREIGN KEY (destination_location_id) REFERENCES locations(id) ON DELETE RESTRICT;
ALTER TABLE route_stops ADD CONSTRAINT fk_route_stops_route_id FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE RESTRICT;
ALTER TABLE route_stops ADD CONSTRAINT fk_route_stops_location_id FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE RESTRICT;
ALTER TABLE seat_layouts ADD CONSTRAINT fk_seat_layouts_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE seat_layout_seats ADD CONSTRAINT fk_seat_layout_seats_layout_id FOREIGN KEY (layout_id) REFERENCES seat_layouts(id) ON DELETE RESTRICT;
ALTER TABLE seat_adjacencies ADD CONSTRAINT fk_seat_adjacencies_layout_id FOREIGN KEY (layout_id) REFERENCES seat_layouts(id) ON DELETE RESTRICT;
ALTER TABLE seat_adjacencies ADD CONSTRAINT fk_seat_adjacencies_seat_a_id FOREIGN KEY (seat_a_id) REFERENCES seat_layout_seats(id) ON DELETE RESTRICT;
ALTER TABLE seat_adjacencies ADD CONSTRAINT fk_seat_adjacencies_seat_b_id FOREIGN KEY (seat_b_id) REFERENCES seat_layout_seats(id) ON DELETE RESTRICT;
ALTER TABLE vehicles ADD CONSTRAINT fk_vehicles_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE vehicles ADD CONSTRAINT fk_vehicles_operator_id FOREIGN KEY (operator_id) REFERENCES transport_operators(id) ON DELETE RESTRICT;
ALTER TABLE vehicles ADD CONSTRAINT fk_vehicles_seat_layout_id FOREIGN KEY (seat_layout_id) REFERENCES seat_layouts(id) ON DELETE RESTRICT;
ALTER TABLE drivers ADD CONSTRAINT fk_drivers_operator_id FOREIGN KEY (operator_id) REFERENCES transport_operators(id) ON DELETE RESTRICT;
ALTER TABLE policy_versions ADD CONSTRAINT fk_policy_versions_template_id FOREIGN KEY (template_id) REFERENCES policy_templates(id) ON DELETE RESTRICT;
ALTER TABLE policy_versions ADD CONSTRAINT fk_policy_versions_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE policy_acceptances ADD CONSTRAINT fk_policy_acceptances_policy_version_id FOREIGN KEY (policy_version_id) REFERENCES policy_versions(id) ON DELETE RESTRICT;
ALTER TABLE policy_acceptances ADD CONSTRAINT fk_policy_acceptances_accepted_by_user_id FOREIGN KEY (accepted_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE configuration_values ADD CONSTRAINT fk_configuration_values_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE configuration_values ADD CONSTRAINT fk_configuration_values_approved_by FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE trips ADD CONSTRAINT fk_trips_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE trips ADD CONSTRAINT fk_trips_branch_id FOREIGN KEY (branch_id) REFERENCES office_branches(id) ON DELETE RESTRICT;
ALTER TABLE trips ADD CONSTRAINT fk_trips_operator_id FOREIGN KEY (operator_id) REFERENCES transport_operators(id) ON DELETE RESTRICT;
ALTER TABLE trips ADD CONSTRAINT fk_trips_route_id FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE RESTRICT;
ALTER TABLE trips ADD CONSTRAINT fk_trips_vehicle_id FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE RESTRICT;
ALTER TABLE trips ADD CONSTRAINT fk_trips_seat_layout_id FOREIGN KEY (seat_layout_id) REFERENCES seat_layouts(id) ON DELETE RESTRICT;
ALTER TABLE trips ADD CONSTRAINT fk_trips_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE trip_stops ADD CONSTRAINT fk_trip_stops_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE trip_stops ADD CONSTRAINT fk_trip_stops_location_id FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE RESTRICT;
ALTER TABLE trip_seats ADD CONSTRAINT fk_trip_seats_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE trip_seats ADD CONSTRAINT fk_trip_seats_layout_seat_id FOREIGN KEY (layout_seat_id) REFERENCES seat_layout_seats(id) ON DELETE RESTRICT;
ALTER TABLE seat_holds ADD CONSTRAINT fk_seat_holds_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE seat_holds ADD CONSTRAINT fk_seat_holds_trip_seat_id FOREIGN KEY (trip_seat_id) REFERENCES trip_seats(id) ON DELETE RESTRICT;
ALTER TABLE seat_holds ADD CONSTRAINT fk_seat_holds_owner_session_id FOREIGN KEY (owner_session_id) REFERENCES user_sessions(id) ON DELETE RESTRICT;
ALTER TABLE bookings ADD CONSTRAINT fk_bookings_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE bookings ADD CONSTRAINT fk_bookings_branch_id FOREIGN KEY (branch_id) REFERENCES office_branches(id) ON DELETE RESTRICT;
ALTER TABLE bookings ADD CONSTRAINT fk_bookings_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE bookings ADD CONSTRAINT fk_bookings_customer_user_id FOREIGN KEY (customer_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE bookings ADD CONSTRAINT fk_bookings_created_by_user_id FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE booking_passengers ADD CONSTRAINT fk_booking_passengers_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE seat_assignments ADD CONSTRAINT fk_seat_assignments_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE seat_assignments ADD CONSTRAINT fk_seat_assignments_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE seat_assignments ADD CONSTRAINT fk_seat_assignments_passenger_id FOREIGN KEY (passenger_id) REFERENCES booking_passengers(id) ON DELETE RESTRICT;
ALTER TABLE seat_assignments ADD CONSTRAINT fk_seat_assignments_trip_seat_id FOREIGN KEY (trip_seat_id) REFERENCES trip_seats(id) ON DELETE RESTRICT;
ALTER TABLE seat_assignments ADD CONSTRAINT fk_seat_assignments_superseded_by_id FOREIGN KEY (superseded_by_id) REFERENCES seat_assignments(id) ON DELETE RESTRICT;
ALTER TABLE tickets ADD CONSTRAINT fk_tickets_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE tickets ADD CONSTRAINT fk_tickets_passenger_id FOREIGN KEY (passenger_id) REFERENCES booking_passengers(id) ON DELETE RESTRICT;
ALTER TABLE tickets ADD CONSTRAINT fk_tickets_seat_assignment_id FOREIGN KEY (seat_assignment_id) REFERENCES seat_assignments(id) ON DELETE RESTRICT;
ALTER TABLE boarding_events ADD CONSTRAINT fk_boarding_events_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE boarding_events ADD CONSTRAINT fk_boarding_events_passenger_id FOREIGN KEY (passenger_id) REFERENCES booking_passengers(id) ON DELETE RESTRICT;
ALTER TABLE boarding_events ADD CONSTRAINT fk_boarding_events_ticket_id FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE RESTRICT;
ALTER TABLE boarding_events ADD CONSTRAINT fk_boarding_events_actor_user_id FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE boarding_events ADD CONSTRAINT fk_boarding_events_device_id FOREIGN KEY (device_id) REFERENCES user_devices(id) ON DELETE RESTRICT;
ALTER TABLE trip_manifests ADD CONSTRAINT fk_trip_manifests_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE trip_manifests ADD CONSTRAINT fk_trip_manifests_generated_by FOREIGN KEY (generated_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE payment_intents ADD CONSTRAINT fk_payment_intents_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE payment_intents ADD CONSTRAINT fk_payment_intents_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE payment_transactions ADD CONSTRAINT fk_payment_transactions_payment_intent_id FOREIGN KEY (payment_intent_id) REFERENCES payment_intents(id) ON DELETE RESTRICT;
ALTER TABLE manual_payment_submissions ADD CONSTRAINT fk_manual_payment_submissions_payment_intent_id FOREIGN KEY (payment_intent_id) REFERENCES payment_intents(id) ON DELETE RESTRICT;
ALTER TABLE manual_payment_submissions ADD CONSTRAINT fk_manual_payment_submissions_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE refunds ADD CONSTRAINT fk_refunds_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE refunds ADD CONSTRAINT fk_refunds_payment_intent_id FOREIGN KEY (payment_intent_id) REFERENCES payment_intents(id) ON DELETE RESTRICT;
ALTER TABLE refunds ADD CONSTRAINT fk_refunds_requested_by FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE refunds ADD CONSTRAINT fk_refunds_approved_by FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE disputes ADD CONSTRAINT fk_disputes_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE disputes ADD CONSTRAINT fk_disputes_assigned_to FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE chargebacks ADD CONSTRAINT fk_chargebacks_payment_transaction_id FOREIGN KEY (payment_transaction_id) REFERENCES payment_transactions(id) ON DELETE RESTRICT;
ALTER TABLE ledger_accounts ADD CONSTRAINT fk_ledger_accounts_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE ledger_entries ADD CONSTRAINT fk_ledger_entries_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE ledger_entries ADD CONSTRAINT fk_ledger_entries_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE ledger_entries ADD CONSTRAINT fk_ledger_entries_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE ledger_entries ADD CONSTRAINT fk_ledger_entries_reversal_of_id FOREIGN KEY (reversal_of_id) REFERENCES ledger_entries(id) ON DELETE RESTRICT;
ALTER TABLE ledger_postings ADD CONSTRAINT fk_ledger_postings_entry_id FOREIGN KEY (entry_id) REFERENCES ledger_entries(id) ON DELETE RESTRICT;
ALTER TABLE ledger_postings ADD CONSTRAINT fk_ledger_postings_account_id FOREIGN KEY (account_id) REFERENCES ledger_accounts(id) ON DELETE RESTRICT;
ALTER TABLE commissions ADD CONSTRAINT fk_commissions_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE commissions ADD CONSTRAINT fk_commissions_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE settlements ADD CONSTRAINT fk_settlements_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE settlements ADD CONSTRAINT fk_settlements_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE settlements ADD CONSTRAINT fk_settlements_approved_by FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE settlement_items ADD CONSTRAINT fk_settlement_items_settlement_id FOREIGN KEY (settlement_id) REFERENCES settlements(id) ON DELETE RESTRICT;
ALTER TABLE support_cases ADD CONSTRAINT fk_support_cases_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE support_cases ADD CONSTRAINT fk_support_cases_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE support_cases ADD CONSTRAINT fk_support_cases_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE support_cases ADD CONSTRAINT fk_support_cases_opened_by_user_id FOREIGN KEY (opened_by_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE support_cases ADD CONSTRAINT fk_support_cases_owner_user_id FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE support_messages ADD CONSTRAINT fk_support_messages_case_id FOREIGN KEY (case_id) REFERENCES support_cases(id) ON DELETE RESTRICT;
ALTER TABLE support_messages ADD CONSTRAINT fk_support_messages_sender_user_id FOREIGN KEY (sender_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE notification_deliveries ADD CONSTRAINT fk_notification_deliveries_notification_id FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE RESTRICT;
ALTER TABLE audit_logs ADD CONSTRAINT fk_audit_logs_actor_user_id FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE audit_logs ADD CONSTRAINT fk_audit_logs_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE data_subject_requests ADD CONSTRAINT fk_data_subject_requests_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE legal_holds ADD CONSTRAINT fk_legal_holds_placed_by FOREIGN KEY (placed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE legal_holds ADD CONSTRAINT fk_legal_holds_released_by FOREIGN KEY (released_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE commission_profiles ADD CONSTRAINT fk_commission_profiles_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE office_subscriptions ADD CONSTRAINT fk_office_subscriptions_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE office_subscriptions ADD CONSTRAINT fk_office_subscriptions_plan_id FOREIGN KEY (plan_id) REFERENCES subscription_plans(id) ON DELETE RESTRICT;
ALTER TABLE subscription_invoices ADD CONSTRAINT fk_subscription_invoices_office_subscription_id FOREIGN KEY (office_subscription_id) REFERENCES office_subscriptions(id) ON DELETE RESTRICT;
ALTER TABLE subscription_invoices ADD CONSTRAINT fk_subscription_invoices_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE subscription_invoices ADD CONSTRAINT fk_subscription_invoices_ledger_entry_id FOREIGN KEY (ledger_entry_id) REFERENCES ledger_entries(id) ON DELETE RESTRICT;
ALTER TABLE stored_files ADD CONSTRAINT fk_stored_files_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE support_attachments ADD CONSTRAINT fk_support_attachments_case_id FOREIGN KEY (case_id) REFERENCES support_cases(id) ON DELETE RESTRICT;
ALTER TABLE support_attachments ADD CONSTRAINT fk_support_attachments_file_id FOREIGN KEY (file_id) REFERENCES stored_files(id) ON DELETE RESTRICT;
ALTER TABLE support_attachments ADD CONSTRAINT fk_support_attachments_uploaded_by FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE trip_incidents ADD CONSTRAINT fk_trip_incidents_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;
ALTER TABLE trip_incidents ADD CONSTRAINT fk_trip_incidents_opened_by FOREIGN KEY (opened_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE office_violations ADD CONSTRAINT fk_office_violations_office_id FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT;
ALTER TABLE office_violations ADD CONSTRAINT fk_office_violations_booking_id FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT;
ALTER TABLE office_violations ADD CONSTRAINT fk_office_violations_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE RESTRICT;

-- Partial unique indexes and high-value indexes
CREATE UNIQUE INDEX uq_users_email ON users(email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX uq_users_phone ON users(phone_e164) WHERE phone_e164 IS NOT NULL;
CREATE UNIQUE INDEX uq_primary_branch ON office_branches(office_id) WHERE is_primary;
CREATE UNIQUE INDEX uq_active_payout ON office_payout_accounts(office_id) WHERE status='active';
CREATE UNIQUE INDEX uq_active_hold_per_seat ON seat_holds(trip_seat_id) WHERE status='active';
CREATE UNIQUE INDEX uq_active_seat_assignment ON seat_assignments(trip_id,trip_seat_id) WHERE status='active';
CREATE UNIQUE INDEX uq_active_passenger_assignment ON seat_assignments(passenger_id) WHERE status='active';
CREATE UNIQUE INDEX uq_active_ticket ON tickets(passenger_id) WHERE status='active';
CREATE UNIQUE INDEX uq_active_legal_hold ON legal_holds(subject_type,subject_id) WHERE active;
CREATE UNIQUE INDEX uq_active_subscription ON office_subscriptions(office_id) WHERE status IN ('trial','active','past_due','grace');
CREATE UNIQUE INDEX uq_membership_nullsafe ON office_memberships(user_id,office_id,branch_id,role_id) NULLS NOT DISTINCT;
CREATE INDEX ix_trip_search ON trips(route_id,scheduled_departure_at,status);
CREATE INDEX ix_booking_office_created ON bookings(office_id,created_at DESC);
CREATE INDEX ix_booking_trip_status ON bookings(trip_id,status);
CREATE INDEX ix_hold_expiry ON seat_holds(expires_at) WHERE status='active';
CREATE INDEX ix_payment_booking_status ON payment_intents(booking_id,status);
CREATE INDEX ix_ledger_office_time ON ledger_entries(office_id,occurred_at);
CREATE INDEX ix_boarding_trip_time ON boarding_events(trip_id,occurred_at);
CREATE INDEX ix_audit_brin ON audit_logs USING BRIN(occurred_at);

-- State-domain checks
ALTER TABLE users ADD CONSTRAINT ck_users_status CHECK (status IN ('active','suspended','disabled','deleted'));
ALTER TABLE offices ADD CONSTRAINT ck_offices_status CHECK (status IN ('draft','submitted','under_review','conditional','active','restricted','no_new_bookings','wind_down','suspended','terminated','archived'));
ALTER TABLE trips ADD CONSTRAINT ck_trips_status CHECK (status IN ('draft','scheduled','published','booking_open','boarding_open','boarding_closed','departed','arrived','completed','cancelled','interrupted'));
ALTER TABLE seat_holds ADD CONSTRAINT ck_seat_holds_status CHECK (status IN ('active','consumed','expired','released'));
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_status CHECK (status IN ('draft','awaiting_payment','confirmed','cancellation_pending','cancelled','completed','no_show','denied_boarding_review'));
ALTER TABLE bookings ADD CONSTRAINT ck_bookings_payment_status CHECK (payment_status IN ('unpaid','pending_verification','partially_paid','paid','partially_refunded','refunded','disputed'));
ALTER TABLE booking_passengers ADD CONSTRAINT ck_passenger_boarding CHECK (boarding_status IN ('not_arrived','arrived','verified','boarded','boarded_reversed','denied','no_show'));
ALTER TABLE seat_assignments ADD CONSTRAINT ck_seat_assignment_status CHECK (status IN ('active','released','moved','cancelled'));
ALTER TABLE tickets ADD CONSTRAINT ck_ticket_status CHECK (status IN ('active','revoked','used','expired'));
ALTER TABLE payment_intents ADD CONSTRAINT ck_payment_intent_status CHECK (status IN ('created','requires_action','pending_verification','succeeded','failed','cancelled','expired'));
ALTER TABLE payment_transactions ADD CONSTRAINT ck_payment_tx_status CHECK (status IN ('pending','succeeded','failed','reversed'));
ALTER TABLE manual_payment_submissions ADD CONSTRAINT ck_manual_payment_status CHECK (status IN ('submitted','verified','rejected','duplicate'));
ALTER TABLE refunds ADD CONSTRAINT ck_refund_status CHECK (status IN ('requested','under_review','approved','processing','succeeded','failed','rejected','cancelled'));
ALTER TABLE disputes ADD CONSTRAINT ck_dispute_status CHECK (status IN ('open','awaiting_office','under_review','decided','appealed','closed'));
ALTER TABLE settlements ADD CONSTRAINT ck_settlement_status CHECK (status IN ('draft','calculated','under_review','approved','processing','paid','failed','closed'));
ALTER TABLE support_cases ADD CONSTRAINT ck_support_status CHECK (status IN ('open','assigned','awaiting_customer','awaiting_office','escalated','resolved','closed','reopened'));
ALTER TABLE notification_deliveries ADD CONSTRAINT ck_delivery_status CHECK (status IN ('queued','sending','sent','delivered','failed','bounced'));
ALTER TABLE verification_cases ADD CONSTRAINT ck_verification_status CHECK (status IN ('draft','submitted','under_review','info_required','external_verification','conditional','approved','rejected','expired'));

-- Null-safe uniqueness for platform/global scopes
CREATE UNIQUE INDEX uq_platform_policy_version ON policy_versions(template_id,version_no,language) WHERE office_id IS NULL;
CREATE UNIQUE INDEX uq_platform_config_effective ON configuration_values(key,effective_from) WHERE scope_type='platform' AND scope_id IS NULL;
CREATE UNIQUE INDEX uq_scoped_config_effective ON configuration_values(scope_type,scope_id,key,effective_from) WHERE scope_id IS NOT NULL;
CREATE UNIQUE INDEX uq_global_ledger_account ON ledger_accounts(code,currency) WHERE office_id IS NULL;

-- Ledger balance enforcement
CREATE OR REPLACE FUNCTION enforce_ledger_entry_balance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d numeric(18,2); c numeric(18,2); target uuid;
BEGIN
  target := COALESCE(NEW.entry_id, OLD.entry_id);
  SELECT COALESCE(SUM(amount) FILTER (WHERE direction='D'),0),
         COALESCE(SUM(amount) FILTER (WHERE direction='C'),0)
    INTO d,c FROM ledger_postings WHERE entry_id=target;
  IF d <> c THEN RAISE EXCEPTION 'LEDGER_UNBALANCED entry=% debit=% credit=%',target,d,c; END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER trg_ledger_balance
AFTER INSERT OR UPDATE OR DELETE ON ledger_postings
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION enforce_ledger_entry_balance();

-- Application must add RLS policies after mapping request user to office membership.
