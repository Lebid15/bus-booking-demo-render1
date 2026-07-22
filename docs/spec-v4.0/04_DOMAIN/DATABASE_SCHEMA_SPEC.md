# مواصفة قاعدة البيانات التفصيلية

> الحالة: **Normative Engineering Specification**  
> قاعدة البيانات: PostgreSQL 18  
> جميع التواريخ: `timestamptz` مخزنة UTC، والعرض حسب منطقة المكتب/المستخدم.  
> المال: `numeric(18,2)` افتراضيًا؛ يمكن رفع المقياس لكل عملة من جدول مرجعي لاحقًا.

## قواعد عامة ملزمة

1. المفاتيح الداخلية UUID عشوائية؛ المعرفات العامة غير متسلسلة.
2. كل جدول متعدد المستأجرين يحمل `office_id` مباشرة أو يمكن عزله عبر علاقة غير قابلة للالتباس.
3. لا يوجد حذف مادي للحجوزات والمدفوعات والقيود والتدقيق؛ تستخدم حالات أو `deleted_at` للبيانات القابلة لذلك.
4. جميع الأوامر الحساسة تنفذ داخل معاملة واحدة، مع Outbox ضمن المعاملة نفسها.
5. تستخدم قيود جزئية فريدة لمنع مقعدين نشطين أو تذكرتين نشطتين أو حساب تسوية نشطين.
6. توازن دفتر الأستاذ يفرض بآلية deferred constraint trigger: مجموع المدين = مجموع الدائن لكل `ledger_entry`.
7. يجب تطبيق Row-Level Security أو QuerySet scoping مركزي، ولا يجوز الاعتماد على `office_id` المرسل من العميل.

## كتالوج الجداول

### `users` — الحسابات البشرية العامة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` | المعرف الداخلي |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` | معرف خارجي ULID/UUID غير متسلسل |
| `email` | `citext` | NULL | `` | البريد بعد التطبيع |
| `phone_e164` | `varchar(20)` | NULL | `` | الهاتف بصيغة دولية عند توفرها |
| `password_hash` | `text` | NULL | `` | لا يستخدم للحسابات الخارجية فقط |
| `full_name` | `varchar(160)` | NOT NULL | `` | الاسم |
| `preferred_language` | `varchar(5)` | NOT NULL | `ar` | ar/en لاحقًا |
| `status` | `varchar(24)` | NOT NULL | `active` | active/suspended/disabled/deleted |
| `is_platform_staff` | `boolean` | NOT NULL | `false` | موظف منصة |
| `email_verified_at` | `timestamptz` | NULL | `` |  |
| `phone_verified_at` | `timestamptz` | NULL | `` |  |
| `last_login_at` | `timestamptz` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `updated_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(email) WHERE email IS NOT NULL`
- `UNIQUE(phone_e164) WHERE phone_e164 IS NOT NULL`
- `CHECK (email IS NOT NULL OR phone_e164 IS NOT NULL)`

### `customer_profiles` — ملف الزبون الاختياري

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `user_id` | `uuid` | PK FK users | `` |  |
| `date_of_birth` | `date` | NULL | `` |  |
| `gender` | `varchar(12)` | NULL | `` | male/female عند الحاجة |
| `nationality_code` | `char(2)` | NULL | `` | ISO-3166 |
| `marketing_consent` | `boolean` | NOT NULL | `false` |  |
| `deleted_at` | `timestamptz` | NULL | `` | تعطيل/إخفاء |

**قيود إضافية:**
- `CHECK (gender IS NULL OR gender IN ('male','female'))`

### `user_sessions` — الجلسات

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `user_id` | `uuid` | FK users NOT NULL | `` |  |
| `token_hash` | `bytea` | UNIQUE NOT NULL | `` |  |
| `device_id` | `uuid` | NULL FK user_devices | `` |  |
| `ip_hash` | `bytea` | NULL | `` | لا يخزن IP خام طويلًا |
| `user_agent` | `text` | NULL | `` |  |
| `expires_at` | `timestamptz` | NOT NULL | `` |  |
| `revoked_at` | `timestamptz` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK (expires_at > created_at)`

### `user_devices` — الأجهزة الموثوقة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `user_id` | `uuid` | FK users NOT NULL | `` |  |
| `device_fingerprint_hash` | `bytea` | NOT NULL | `` |  |
| `label` | `varchar(120)` | NULL | `` |  |
| `trusted_at` | `timestamptz` | NULL | `` |  |
| `last_seen_at` | `timestamptz` | NOT NULL | `now()` |  |
| `revoked_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(user_id, device_fingerprint_hash)`

### `mfa_methods` — وسائل MFA

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `user_id` | `uuid` | FK users NOT NULL | `` |  |
| `method_type` | `varchar(20)` | NOT NULL | `` | totp/webauthn/recovery |
| `secret_ciphertext` | `bytea` | NULL | `` | مشفّر |
| `credential_id` | `bytea` | NULL | `` | WebAuthn |
| `is_primary` | `boolean` | NOT NULL | `false` |  |
| `verified_at` | `timestamptz` | NULL | `` |  |
| `disabled_at` | `timestamptz` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK (method_type IN ('totp','webauthn','recovery'))`

### `roles` — الأدوار المعرفة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `code` | `varchar(80)` | UNIQUE NOT NULL | `` |  |
| `scope_type` | `varchar(20)` | NOT NULL | `` | platform/office/branch |
| `name_ar` | `varchar(120)` | NOT NULL | `` |  |
| `is_system` | `boolean` | NOT NULL | `true` |  |

**قيود إضافية:**
- `CHECK (scope_type IN ('platform','office','branch'))`

### `permissions` — الصلاحيات الذرية

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `code` | `varchar(120)` | UNIQUE NOT NULL | `` |  |
| `name_ar` | `varchar(160)` | NOT NULL | `` |  |
| `risk_level` | `varchar(12)` | NOT NULL | `normal` | normal/sensitive/critical |

**قيود إضافية:**
- `CHECK (risk_level IN ('normal','sensitive','critical'))`

### `role_permissions` — ربط الدور بالصلاحيات

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `role_id` | `uuid` | PK FK roles | `` |  |
| `permission_id` | `uuid` | PK FK permissions | `` |  |

### `transport_operators` — الناقل الفعلي/الشركة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `legal_name` | `varchar(200)` | NOT NULL | `` |  |
| `trade_name` | `varchar(160)` | NULL | `` |  |
| `registration_number` | `varchar(100)` | NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `draft` | draft/under_review/active/restricted/suspended/terminated |
| `country_code` | `char(2)` | NOT NULL | `SY` |  |
| `support_phone` | `varchar(20)` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `updated_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(country_code, registration_number) WHERE registration_number IS NOT NULL`

### `offices` — المكتب البائع المتعاقد

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `operator_id` | `uuid` | NULL FK transport_operators | `` | قد يكون مكتب وكيل مستقل |
| `legal_name` | `varchar(200)` | NOT NULL | `` |  |
| `trade_name` | `varchar(160)` | NOT NULL | `` |  |
| `office_type` | `varchar(24)` | NOT NULL | `` | carrier/branch/authorized_agent/garage_office |
| `status` | `varchar(24)` | NOT NULL | `draft` | draft/submitted/under_review/conditional/active/restricted/no_new_bookings/wind_down/suspended/terminated/archived |
| `timezone` | `varchar(64)` | NOT NULL | `Asia/Damascus` |  |
| `default_currency` | `char(3)` | NOT NULL | `SYP` |  |
| `support_phone` | `varchar(20)` | NOT NULL | `` |  |
| `support_email` | `citext` | NULL | `` |  |
| `commission_profile_id` | `uuid` | NULL FK commission_profiles | `` |  |
| `activated_at` | `timestamptz` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `updated_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK (office_type IN ('carrier','branch','authorized_agent','garage_office'))`

### `office_branches` — فروع المكتب ونقاط التشغيل

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `name` | `varchar(160)` | NOT NULL | `` |  |
| `location_id` | `uuid` | FK locations NOT NULL | `` |  |
| `phone` | `varchar(20)` | NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | active/inactive/suspended |
| `is_primary` | `boolean` | NOT NULL | `false` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(office_id, name)`
- `UNIQUE(office_id) WHERE is_primary=true`

### `office_memberships` — عضوية موظف في مكتب/فرع

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `user_id` | `uuid` | FK users NOT NULL | `` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `branch_id` | `uuid` | NULL FK office_branches | `` |  |
| `role_id` | `uuid` | FK roles NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | invited/active/suspended/revoked |
| `can_approve_own_actions` | `boolean` | NOT NULL | `false` | يجب أن يبقى false للحساس |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `revoked_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(user_id, office_id, branch_id, role_id)`

### `verification_cases` — ملف تحقق المكتب

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `draft` | draft/submitted/under_review/info_required/external_verification/conditional/approved/rejected/expired |
| `risk_level` | `varchar(12)` | NOT NULL | `basic` | basic/documented/enhanced |
| `submitted_at` | `timestamptz` | NULL | `` |  |
| `decided_at` | `timestamptz` | NULL | `` |  |
| `reviewer_user_id` | `uuid` | NULL FK users | `` |  |
| `decision_reason` | `text` | NULL | `` |  |
| `version` | `integer` | NOT NULL | `1` |  |

**قيود إضافية:**
- `UNIQUE(office_id, version)`

### `office_documents` — وثائق المكتب/الناقل

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `verification_case_id` | `uuid` | NULL FK verification_cases | `` |  |
| `document_type` | `varchar(64)` | NOT NULL | `` |  |
| `storage_object_key` | `text` | NOT NULL | `` | خاص |
| `sha256` | `char(64)` | NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `pending` | pending/verified/rejected/expired |
| `issued_at` | `date` | NULL | `` |  |
| `expires_at` | `date` | NULL | `` |  |
| `reviewed_by` | `uuid` | NULL FK users | `` |  |
| `reviewed_at` | `timestamptz` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(office_id, document_type, sha256)`

### `office_payout_accounts` — حسابات تسوية المكتب

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `method_type` | `varchar(30)` | NOT NULL | `` | bank/wallet/cash_clearing |
| `account_holder_name` | `varchar(200)` | NOT NULL | `` |  |
| `account_reference_ciphertext` | `bytea` | NOT NULL | `` |  |
| `account_reference_last4` | `varchar(8)` | NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `pending` | pending/verified/active/suspended/replaced |
| `verified_at` | `timestamptz` | NULL | `` |  |
| `effective_at` | `timestamptz` | NULL | `` |  |
| `created_by` | `uuid` | FK users NOT NULL | `` |  |
| `approved_by` | `uuid` | NULL FK users | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK (approved_by IS NULL OR approved_by <> created_by)`
- `UNIQUE(office_id) WHERE status='active'`

### `locations` — المدن والكراجات والنقاط

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `location_type` | `varchar(20)` | NOT NULL | `` | city/garage/boarding_point/dropoff_point |
| `parent_id` | `uuid` | NULL FK locations | `` |  |
| `name_ar` | `varchar(160)` | NOT NULL | `` |  |
| `name_en` | `varchar(160)` | NULL | `` |  |
| `address_text` | `text` | NULL | `` |  |
| `latitude` | `numeric(9,6)` | NULL | `` |  |
| `longitude` | `numeric(9,6)` | NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | active/inactive |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK (location_type IN ('city','garage','boarding_point','dropoff_point'))`
- `CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90)`
- `CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)`

### `routes` — الخط التجاري

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `origin_location_id` | `uuid` | FK locations NOT NULL | `` |  |
| `destination_location_id` | `uuid` | FK locations NOT NULL | `` |  |
| `name_ar` | `varchar(200)` | NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | active/inactive |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK (origin_location_id <> destination_location_id)`
- `UNIQUE(origin_location_id,destination_location_id)`

### `route_stops` — النقاط الافتراضية لمسار

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `route_id` | `uuid` | PK FK routes | `` |  |
| `sequence_no` | `smallint` | PK NOT NULL | `` |  |
| `location_id` | `uuid` | FK locations NOT NULL | `` |  |
| `stop_type` | `varchar(20)` | NOT NULL | `` | boarding/dropoff/both |
| `offset_minutes` | `integer` | NOT NULL | `0` |  |

**قيود إضافية:**
- `CHECK(sequence_no>0)`
- `UNIQUE(route_id,location_id)`

### `seat_layouts` — قالب مخطط البولمان

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `name` | `varchar(160)` | NOT NULL | `` |  |
| `layout_type` | `varchar(20)` | NOT NULL | `` | 2+2/2+1/custom |
| `seat_count` | `smallint` | NOT NULL | `` |  |
| `version` | `integer` | NOT NULL | `1` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | draft/active/retired |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK(seat_count>0)`
- `UNIQUE(office_id,name,version)`

### `seat_layout_seats` — مقاعد المخطط

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `layout_id` | `uuid` | FK seat_layouts NOT NULL | `` |  |
| `seat_code` | `varchar(12)` | NOT NULL | `` |  |
| `row_no` | `smallint` | NOT NULL | `` |  |
| `column_no` | `smallint` | NOT NULL | `` |  |
| `seat_type` | `varchar(20)` | NOT NULL | `standard` | standard/vip/single/accessible/crew/blocked |
| `is_sellable` | `boolean` | NOT NULL | `true` |  |
| `metadata` | `jsonb` | NOT NULL | `{}` |  |

**قيود إضافية:**
- `UNIQUE(layout_id,seat_code)`
- `UNIQUE(layout_id,row_no,column_no)`
- `CHECK(row_no>0 AND column_no>0)`

### `seat_adjacencies` — تعريف المجاورة المنطقي

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `layout_id` | `uuid` | PK FK seat_layouts | `` |  |
| `seat_a_id` | `uuid` | PK FK seat_layout_seats | `` |  |
| `seat_b_id` | `uuid` | PK FK seat_layout_seats | `` |  |
| `adjacency_type` | `varchar(20)` | NOT NULL | `same_unit` | same_unit/aisle/nearby |

**قيود إضافية:**
- `CHECK(seat_a_id < seat_b_id)`

### `vehicles` — البولمانات

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `operator_id` | `uuid` | NULL FK transport_operators | `` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `plate_number` | `varchar(40)` | NOT NULL | `` |  |
| `fleet_number` | `varchar(40)` | NULL | `` |  |
| `seat_layout_id` | `uuid` | FK seat_layouts NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | active/maintenance/out_of_service/retired |
| `make_model` | `varchar(160)` | NULL | `` |  |
| `year` | `smallint` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(office_id,plate_number)`
- `CHECK(year IS NULL OR year BETWEEN 1980 AND 2100)`

### `drivers` — السائقون

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `operator_id` | `uuid` | FK transport_operators NOT NULL | `` |  |
| `full_name` | `varchar(160)` | NOT NULL | `` |  |
| `phone` | `varchar(20)` | NULL | `` |  |
| `license_number_ciphertext` | `bytea` | NOT NULL | `` |  |
| `license_last4` | `varchar(8)` | NULL | `` |  |
| `license_expires_at` | `date` | NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | active/suspended/expired |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

### `policy_templates` — قوالب السياسات

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `code` | `varchar(80)` | UNIQUE NOT NULL | `` |  |
| `policy_type` | `varchar(40)` | NOT NULL | `` | cancellation/payment/boarding/baggage/terms/privacy |
| `owner_scope` | `varchar(20)` | NOT NULL | `` | platform/office |
| `status` | `varchar(20)` | NOT NULL | `active` | draft/active/retired |

### `policy_versions` — إصدارات السياسات

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `template_id` | `uuid` | FK policy_templates NOT NULL | `` |  |
| `office_id` | `uuid` | NULL FK offices | `` | NULL لسياسة منصة |
| `version_no` | `integer` | NOT NULL | `` |  |
| `language` | `varchar(5)` | NOT NULL | `ar` |  |
| `title` | `varchar(200)` | NOT NULL | `` |  |
| `content_markdown` | `text` | NOT NULL | `` |  |
| `rules_json` | `jsonb` | NOT NULL | `{}` | نسخة آلة قابلة للتطبيق |
| `effective_from` | `timestamptz` | NOT NULL | `` |  |
| `effective_to` | `timestamptz` | NULL | `` |  |
| `published_at` | `timestamptz` | NULL | `` |  |
| `content_sha256` | `char(64)` | NOT NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(template_id,office_id,version_no,language)`
- `CHECK(effective_to IS NULL OR effective_to>effective_from)`

### `policy_acceptances` — الموافقات على السياسات

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `policy_version_id` | `uuid` | FK policy_versions NOT NULL | `` |  |
| `subject_type` | `varchar(20)` | NOT NULL | `` | user/office/booking |
| `subject_id` | `uuid` | NOT NULL | `` |  |
| `accepted_by_user_id` | `uuid` | NULL FK users | `` |  |
| `accepted_at` | `timestamptz` | NOT NULL | `now()` |  |
| `ip_hash` | `bytea` | NULL | `` |  |
| `user_agent_hash` | `bytea` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(policy_version_id,subject_type,subject_id)`

### `configuration_values` — إعدادات قابلة للتغيير

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `scope_type` | `varchar(20)` | NOT NULL | `` | platform/office/branch/route/trip |
| `scope_id` | `uuid` | NULL | `` | NULL للمنصة |
| `key` | `varchar(120)` | NOT NULL | `` |  |
| `value_json` | `jsonb` | NOT NULL | `` |  |
| `value_type` | `varchar(20)` | NOT NULL | `` | boolean/integer/decimal/string/duration/object |
| `effective_from` | `timestamptz` | NOT NULL | `now()` |  |
| `effective_to` | `timestamptz` | NULL | `` |  |
| `created_by` | `uuid` | FK users NOT NULL | `` |  |
| `approved_by` | `uuid` | NULL FK users | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(scope_type,scope_id,key,effective_from)`
- `CHECK(effective_to IS NULL OR effective_to>effective_from)`

### `trips` — نسخة تشغيلية لرحلة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `branch_id` | `uuid` | FK office_branches NOT NULL | `` |  |
| `operator_id` | `uuid` | FK transport_operators NOT NULL | `` |  |
| `route_id` | `uuid` | FK routes NOT NULL | `` |  |
| `vehicle_id` | `uuid` | FK vehicles NOT NULL | `` |  |
| `seat_layout_id` | `uuid` | FK seat_layouts NOT NULL | `` | Snapshot مرجعي |
| `status` | `varchar(24)` | NOT NULL | `draft` | draft/scheduled/published/booking_open/boarding_open/boarding_closed/departed/arrived/completed/cancelled/interrupted |
| `scheduled_departure_at` | `timestamptz` | NOT NULL | `` |  |
| `scheduled_arrival_at` | `timestamptz` | NULL | `` |  |
| `actual_departure_at` | `timestamptz` | NULL | `` |  |
| `actual_arrival_at` | `timestamptz` | NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `base_price` | `numeric(18,2)` | NOT NULL | `` |  |
| `booking_open_at` | `timestamptz` | NULL | `` |  |
| `booking_close_at` | `timestamptz` | NULL | `` |  |
| `boarding_open_at` | `timestamptz` | NULL | `` |  |
| `boarding_close_at` | `timestamptz` | NULL | `` |  |
| `policy_snapshot` | `jsonb` | NOT NULL | `{}` |  |
| `pricing_snapshot` | `jsonb` | NOT NULL | `{}` |  |
| `version` | `integer` | NOT NULL | `1` | Optimistic lock |
| `created_by` | `uuid` | FK users NOT NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `updated_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK(scheduled_arrival_at IS NULL OR scheduled_arrival_at>scheduled_departure_at)`
- `CHECK(base_price>=0)`
- `CHECK(booking_close_at IS NULL OR booking_close_at<=scheduled_departure_at)`

### `trip_stops` — نقاط الرحلة الفعلية

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `trip_id` | `uuid` | FK trips NOT NULL | `` |  |
| `sequence_no` | `smallint` | NOT NULL | `` |  |
| `location_id` | `uuid` | FK locations NOT NULL | `` |  |
| `scheduled_at` | `timestamptz` | NULL | `` |  |
| `actual_at` | `timestamptz` | NULL | `` |  |
| `stop_type` | `varchar(20)` | NOT NULL | `` | boarding/dropoff/both |

**قيود إضافية:**
- `UNIQUE(trip_id,sequence_no)`
- `UNIQUE(trip_id,location_id)`
- `CHECK(sequence_no>0)`

### `trip_seats` — مخزون المقاعد لكل رحلة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `trip_id` | `uuid` | FK trips NOT NULL | `` |  |
| `layout_seat_id` | `uuid` | FK seat_layout_seats NOT NULL | `` |  |
| `seat_code` | `varchar(12)` | NOT NULL | `` | Snapshot |
| `seat_type` | `varchar(20)` | NOT NULL | `` |  |
| `sellable` | `boolean` | NOT NULL | `true` |  |
| `blocked_reason` | `varchar(160)` | NULL | `` |  |
| `version` | `integer` | NOT NULL | `1` |  |

**قيود إضافية:**
- `UNIQUE(trip_id,layout_seat_id)`
- `UNIQUE(trip_id,seat_code)`

### `seat_holds` — حجز مؤقت للمقعد

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `trip_id` | `uuid` | FK trips NOT NULL | `` |  |
| `trip_seat_id` | `uuid` | FK trip_seats NOT NULL | `` |  |
| `hold_token_hash` | `bytea` | UNIQUE NOT NULL | `` |  |
| `owner_session_id` | `uuid` | NULL FK user_sessions | `` |  |
| `owner_booking_draft_id` | `uuid` | NULL | `` |  |
| `status` | `varchar(16)` | NOT NULL | `active` | active/consumed/expired/released |
| `expires_at` | `timestamptz` | NOT NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `released_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(trip_seat_id) WHERE status='active'`
- `CHECK(expires_at>created_at)`

### `bookings` — الحجز الرئيسي

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `pnr` | `varchar(12)` | UNIQUE NOT NULL | `` | غير متسلسل وعشوائي |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `branch_id` | `uuid` | FK office_branches NOT NULL | `` |  |
| `trip_id` | `uuid` | FK trips NOT NULL | `` |  |
| `customer_user_id` | `uuid` | NULL FK users | `` |  |
| `source` | `varchar(24)` | NOT NULL | `` | public_web/office/phone/import |
| `status` | `varchar(32)` | NOT NULL | `draft` | draft/awaiting_payment/confirmed/cancellation_pending/cancelled/completed/no_show/denied_boarding_review |
| `payment_status` | `varchar(24)` | NOT NULL | `unpaid` | unpaid/pending_verification/partially_paid/paid/partially_refunded/refunded/disputed |
| `contact_name` | `varchar(160)` | NOT NULL | `` |  |
| `contact_phone` | `varchar(20)` | NOT NULL | `` |  |
| `contact_email` | `citext` | NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `subtotal_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `discount_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `fee_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `total_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `paid_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `refunded_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `payment_deadline_at` | `timestamptz` | NULL | `` |  |
| `policy_snapshot` | `jsonb` | NOT NULL | `` |  |
| `pricing_snapshot` | `jsonb` | NOT NULL | `` |  |
| `commission_snapshot` | `jsonb` | NOT NULL | `` |  |
| `terms_version_ids` | `uuid[]` | NOT NULL | `{}` |  |
| `manage_token_hash` | `bytea` | UNIQUE NOT NULL | `` |  |
| `version` | `integer` | NOT NULL | `1` |  |
| `confirmed_at` | `timestamptz` | NULL | `` |  |
| `cancelled_at` | `timestamptz` | NULL | `` |  |
| `created_by_user_id` | `uuid` | NULL FK users | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `updated_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK(subtotal_amount>=0 AND discount_amount>=0 AND fee_amount>=0 AND total_amount>=0)`
- `CHECK(total_amount=subtotal_amount-discount_amount+fee_amount)`
- `CHECK(paid_amount>=0 AND refunded_amount>=0 AND refunded_amount<=paid_amount)`

### `booking_passengers` — ركاب الحجز

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `booking_id` | `uuid` | FK bookings NOT NULL | `` |  |
| `sequence_no` | `smallint` | NOT NULL | `` |  |
| `full_name` | `varchar(160)` | NOT NULL | `` |  |
| `gender` | `varchar(12)` | NOT NULL | `` | male/female |
| `passenger_type` | `varchar(16)` | NOT NULL | `adult` | adult/child/infant |
| `date_of_birth` | `date` | NULL | `` |  |
| `nationality_code` | `char(2)` | NULL | `` |  |
| `identity_type` | `varchar(24)` | NULL | `` |  |
| `identity_number_normalized` | `varchar(80)` | NULL | `` | يفضل مشفر/هاش حسب الحاجة |
| `boarding_status` | `varchar(28)` | NOT NULL | `not_arrived` | not_arrived/arrived/verified/boarded/boarded_reversed/denied/no_show |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(booking_id,sequence_no)`
- `CHECK(gender IN ('male','female'))`
- `CHECK(passenger_type IN ('adult','child','infant'))`

### `seat_assignments` — تخصيص المقعد النهائي

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `trip_id` | `uuid` | FK trips NOT NULL | `` |  |
| `booking_id` | `uuid` | FK bookings NOT NULL | `` |  |
| `passenger_id` | `uuid` | FK booking_passengers NOT NULL | `` |  |
| `trip_seat_id` | `uuid` | FK trip_seats NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | active/released/moved/cancelled |
| `price_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `assigned_at` | `timestamptz` | NOT NULL | `now()` |  |
| `released_at` | `timestamptz` | NULL | `` |  |
| `superseded_by_id` | `uuid` | NULL FK seat_assignments | `` |  |

**قيود إضافية:**
- `UNIQUE(trip_id,trip_seat_id) WHERE status='active'`
- `UNIQUE(passenger_id) WHERE status='active'`
- `CHECK(price_amount>=0)`

### `tickets` — إصدارات التذاكر

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `booking_id` | `uuid` | FK bookings NOT NULL | `` |  |
| `passenger_id` | `uuid` | FK booking_passengers NOT NULL | `` |  |
| `seat_assignment_id` | `uuid` | FK seat_assignments NOT NULL | `` |  |
| `version_no` | `integer` | NOT NULL | `1` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | active/revoked/used/expired |
| `qr_token_hash` | `bytea` | UNIQUE NOT NULL | `` |  |
| `qr_payload_signature` | `bytea` | NOT NULL | `` |  |
| `issued_at` | `timestamptz` | NOT NULL | `now()` |  |
| `revoked_at` | `timestamptz` | NULL | `` |  |
| `used_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(passenger_id,version_no)`
- `UNIQUE(passenger_id) WHERE status='active'`

### `boarding_events` — أحداث الصعود غير القابلة للتعديل

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `trip_id` | `uuid` | FK trips NOT NULL | `` |  |
| `passenger_id` | `uuid` | FK booking_passengers NOT NULL | `` |  |
| `ticket_id` | `uuid` | NULL FK tickets | `` |  |
| `event_type` | `varchar(24)` | NOT NULL | `` | arrived/verified/boarded/reversed/denied/no_show/manual_check |
| `occurred_at` | `timestamptz` | NOT NULL | `now()` |  |
| `actor_user_id` | `uuid` | NULL FK users | `` |  |
| `device_id` | `uuid` | NULL FK user_devices | `` |  |
| `offline_event_id` | `varchar(80)` | NULL | `` |  |
| `reason_code` | `varchar(80)` | NULL | `` |  |
| `metadata` | `jsonb` | NOT NULL | `{}` |  |

**قيود إضافية:**
- `UNIQUE(device_id,offline_event_id) WHERE offline_event_id IS NOT NULL`

### `trip_manifests` — إصدارات قائمة الركاب

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `trip_id` | `uuid` | FK trips NOT NULL | `` |  |
| `version_no` | `integer` | NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `` | draft/boarding_closed/final |
| `manifest_json` | `jsonb` | NOT NULL | `` |  |
| `sha256` | `char(64)` | NOT NULL | `` |  |
| `generated_at` | `timestamptz` | NOT NULL | `now()` |  |
| `generated_by` | `uuid` | NULL FK users | `` |  |

**قيود إضافية:**
- `UNIQUE(trip_id,version_no)`

### `payment_intents` — نية دفع

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `booking_id` | `uuid` | FK bookings NOT NULL | `` |  |
| `method_type` | `varchar(30)` | NOT NULL | `` | office_cash/manual_transfer/electronic |
| `status` | `varchar(24)` | NOT NULL | `created` | created/requires_action/pending_verification/succeeded/failed/cancelled/expired |
| `amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `provider_code` | `varchar(60)` | NULL | `` |  |
| `provider_reference` | `varchar(160)` | NULL | `` |  |
| `idempotency_key` | `varchar(120)` | NOT NULL | `` |  |
| `expires_at` | `timestamptz` | NULL | `` |  |
| `created_by` | `uuid` | NULL FK users | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `updated_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(booking_id,idempotency_key)`
- `UNIQUE(provider_code,provider_reference) WHERE provider_reference IS NOT NULL`
- `CHECK(amount>0)`

### `payment_transactions` — الحركات المالية الخارجية/النقدية

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `payment_intent_id` | `uuid` | FK payment_intents NOT NULL | `` |  |
| `transaction_type` | `varchar(20)` | NOT NULL | `` | authorize/capture/payment/reversal |
| `status` | `varchar(20)` | NOT NULL | `` | pending/succeeded/failed/reversed |
| `amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `provider_event_id` | `varchar(160)` | NULL | `` |  |
| `occurred_at` | `timestamptz` | NOT NULL | `` | وقت الحركة الحقيقي |
| `recorded_at` | `timestamptz` | NOT NULL | `now()` |  |
| `raw_reference_hash` | `bytea` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(provider_event_id) WHERE provider_event_id IS NOT NULL`
- `CHECK(amount>0)`

### `manual_payment_submissions` — إثبات التحويل اليدوي

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `payment_intent_id` | `uuid` | FK payment_intents NOT NULL | `` |  |
| `sender_reference` | `varchar(160)` | NULL | `` |  |
| `transfer_reference` | `varchar(160)` | NOT NULL | `` |  |
| `transferred_at` | `timestamptz` | NOT NULL | `` |  |
| `amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `proof_object_key` | `text` | NULL | `` |  |
| `proof_sha256` | `char(64)` | NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `submitted` | submitted/verified/rejected/duplicate |
| `submitted_at` | `timestamptz` | NOT NULL | `now()` |  |
| `reviewed_by` | `uuid` | NULL FK users | `` |  |
| `reviewed_at` | `timestamptz` | NULL | `` |  |
| `rejection_reason` | `text` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(transfer_reference)`
- `UNIQUE(proof_sha256) WHERE proof_sha256 IS NOT NULL`
- `CHECK(amount>0)`

### `refunds` — طلبات ونتائج الاسترداد

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `booking_id` | `uuid` | FK bookings NOT NULL | `` |  |
| `payment_intent_id` | `uuid` | NULL FK payment_intents | `` |  |
| `status` | `varchar(24)` | NOT NULL | `requested` | requested/under_review/approved/processing/succeeded/failed/rejected/cancelled |
| `reason_code` | `varchar(80)` | NOT NULL | `` |  |
| `requested_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `approved_amount` | `numeric(18,2)` | NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `requested_by` | `uuid` | NULL FK users | `` |  |
| `approved_by` | `uuid` | NULL FK users | `` |  |
| `provider_reference` | `varchar(160)` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `completed_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(requested_amount>0)`
- `CHECK(approved_amount IS NULL OR approved_amount BETWEEN 0 AND requested_amount)`
- `CHECK(approved_by IS NULL OR approved_by<>requested_by)`

### `disputes` — نزاع داخلي

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `booking_id` | `uuid` | FK bookings NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `open` | open/awaiting_office/under_review/decided/appealed/closed |
| `category` | `varchar(60)` | NOT NULL | `` |  |
| `disputed_amount` | `numeric(18,2)` | NULL | `` |  |
| `opened_by_type` | `varchar(20)` | NOT NULL | `` | customer/office/platform |
| `opened_by_id` | `uuid` | NULL | `` |  |
| `assigned_to` | `uuid` | NULL FK users | `` |  |
| `decision_code` | `varchar(80)` | NULL | `` |  |
| `decision_summary` | `text` | NULL | `` |  |
| `opened_at` | `timestamptz` | NOT NULL | `now()` |  |
| `decided_at` | `timestamptz` | NULL | `` |  |
| `closed_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(disputed_amount IS NULL OR disputed_amount>=0)`

### `chargebacks` — اعتراض مزود الدفع

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `payment_transaction_id` | `uuid` | FK payment_transactions NOT NULL | `` |  |
| `provider_case_id` | `varchar(160)` | UNIQUE NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `` | open/evidence_submitted/won/lost/accepted/closed |
| `amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `deadline_at` | `timestamptz` | NULL | `` |  |
| `opened_at` | `timestamptz` | NOT NULL | `` |  |
| `closed_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(amount>0)`

### `ledger_accounts` — دليل حسابات داخلي

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | NULL FK offices | `` | NULL لحسابات المنصة العامة |
| `code` | `varchar(80)` | NOT NULL | `` |  |
| `account_type` | `varchar(20)` | NOT NULL | `` | asset/liability/equity/revenue/expense/contra |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | active/closed |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(office_id,code,currency)`

### `ledger_entries` — رأس القيد المحاسبي

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `event_type` | `varchar(80)` | NOT NULL | `` |  |
| `event_id` | `uuid` | NOT NULL | `` | معرف الحدث التجاري |
| `booking_id` | `uuid` | NULL FK bookings | `` |  |
| `trip_id` | `uuid` | NULL FK trips | `` |  |
| `office_id` | `uuid` | NULL FK offices | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `status` | `varchar(16)` | NOT NULL | `posted` | posted/reversed |
| `occurred_at` | `timestamptz` | NOT NULL | `` |  |
| `posted_at` | `timestamptz` | NOT NULL | `now()` |  |
| `reversal_of_id` | `uuid` | NULL FK ledger_entries | `` |  |
| `description` | `text` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(event_type,event_id,currency)`
- `CHECK(reversal_of_id IS NULL OR status='reversed')`

### `ledger_postings` — طرفا القيد

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `entry_id` | `uuid` | FK ledger_entries NOT NULL | `` |  |
| `account_id` | `uuid` | FK ledger_accounts NOT NULL | `` |  |
| `direction` | `char(1)` | NOT NULL | `` | D/C |
| `amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `memo` | `varchar(240)` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(direction IN ('D','C'))`
- `CHECK(amount>0)`

### `commissions` — استحقاق عمولة الحجز

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `booking_id` | `uuid` | FK bookings NOT NULL | `` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `expected` | expected/pending/earned/in_settlement/paid/reversed/adjusted |
| `basis_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `rate` | `numeric(9,6)` | NOT NULL | `` |  |
| `fixed_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `commission_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `earned_at` | `timestamptz` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(booking_id)`
- `CHECK(basis_amount>=0 AND rate>=0 AND fixed_amount>=0 AND commission_amount>=0)`

### `settlements` — دفعة تسوية لمكتب

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `period_start` | `date` | NOT NULL | `` |  |
| `period_end` | `date` | NOT NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `draft` | draft/calculated/under_review/approved/processing/paid/failed/closed |
| `gross_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `commission_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `refund_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `reserve_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `adjustment_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `net_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `created_by` | `uuid` | FK users NOT NULL | `` |  |
| `approved_by` | `uuid` | NULL FK users | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `paid_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(office_id,period_start,period_end,currency)`
- `CHECK(period_end>=period_start)`
- `CHECK(approved_by IS NULL OR approved_by<>created_by)`

### `settlement_items` — تفاصيل التسوية

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `settlement_id` | `uuid` | FK settlements NOT NULL | `` |  |
| `item_type` | `varchar(40)` | NOT NULL | `` | booking_proceeds/commission/refund/reserve/adjustment/direct_payment_commission |
| `source_type` | `varchar(40)` | NOT NULL | `` |  |
| `source_id` | `uuid` | NOT NULL | `` |  |
| `amount` | `numeric(18,2)` | NOT NULL | `` | موجب/سالب بحسب النوع |
| `description` | `varchar(240)` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(settlement_id,item_type,source_type,source_id)`

### `support_cases` — حالات الدعم

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `booking_id` | `uuid` | NULL FK bookings | `` |  |
| `trip_id` | `uuid` | NULL FK trips | `` |  |
| `office_id` | `uuid` | NULL FK offices | `` |  |
| `opened_by_user_id` | `uuid` | NULL FK users | `` |  |
| `priority` | `varchar(8)` | NOT NULL | `P3` | P0-P4 |
| `category` | `varchar(60)` | NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `open` | open/assigned/awaiting_customer/awaiting_office/escalated/resolved/closed/reopened |
| `owner_user_id` | `uuid` | NULL FK users | `` |  |
| `sla_due_at` | `timestamptz` | NULL | `` |  |
| `resolution_code` | `varchar(80)` | NULL | `` |  |
| `opened_at` | `timestamptz` | NOT NULL | `now()` |  |
| `resolved_at` | `timestamptz` | NULL | `` |  |
| `closed_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(priority IN ('P0','P1','P2','P3','P4'))`

### `support_messages` — رسائل الحالة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `case_id` | `uuid` | FK support_cases NOT NULL | `` |  |
| `sender_type` | `varchar(20)` | NOT NULL | `` | customer/office/platform/system |
| `sender_user_id` | `uuid` | NULL FK users | `` |  |
| `body` | `text` | NOT NULL | `` |  |
| `visibility` | `varchar(20)` | NOT NULL | `shared` | shared/internal |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

### `notifications` — الإشعار المنطقي

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `event_type` | `varchar(80)` | NOT NULL | `` |  |
| `recipient_type` | `varchar(20)` | NOT NULL | `` | user/office/booking_contact |
| `recipient_id` | `uuid` | NULL | `` |  |
| `booking_id` | `uuid` | NULL FK bookings | `` |  |
| `template_code` | `varchar(80)` | NOT NULL | `` |  |
| `language` | `varchar(5)` | NOT NULL | `ar` |  |
| `payload` | `jsonb` | NOT NULL | `{}` |  |
| `status` | `varchar(20)` | NOT NULL | `queued` | queued/partially_sent/sent/failed/cancelled |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

### `notification_deliveries` — محاولات القنوات

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `notification_id` | `uuid` | FK notifications NOT NULL | `` |  |
| `channel` | `varchar(20)` | NOT NULL | `` | in_app/email/sms/push |
| `destination_hash` | `bytea` | NULL | `` |  |
| `provider_message_id` | `varchar(160)` | NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `queued` | queued/sending/sent/delivered/failed/bounced |
| `attempt_no` | `smallint` | NOT NULL | `1` |  |
| `next_attempt_at` | `timestamptz` | NULL | `` |  |
| `sent_at` | `timestamptz` | NULL | `` |  |
| `delivered_at` | `timestamptz` | NULL | `` |  |
| `error_code` | `varchar(80)` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(notification_id,channel,attempt_no)`

### `risk_assessments` — تقييم خطر

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `subject_type` | `varchar(30)` | NOT NULL | `` | booking/payment/user/office/employee/device |
| `subject_id` | `uuid` | NOT NULL | `` |  |
| `score` | `numeric(6,3)` | NOT NULL | `` | 0-100 |
| `decision` | `varchar(24)` | NOT NULL | `` | allow/step_up/manual_review/restrict/block |
| `model_version` | `varchar(40)` | NOT NULL | `` |  |
| `signals` | `jsonb` | NOT NULL | `{}` |  |
| `review_status` | `varchar(20)` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK(score BETWEEN 0 AND 100)`

### `audit_logs` — سجل التدقيق

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `bigserial` | PK | `` |  |
| `occurred_at` | `timestamptz` | NOT NULL | `now()` |  |
| `actor_user_id` | `uuid` | NULL FK users | `` |  |
| `actor_type` | `varchar(20)` | NOT NULL | `` | user/system/provider |
| `office_id` | `uuid` | NULL FK offices | `` |  |
| `action` | `varchar(120)` | NOT NULL | `` |  |
| `object_type` | `varchar(80)` | NOT NULL | `` |  |
| `object_id` | `uuid` | NULL | `` |  |
| `request_id` | `uuid` | NULL | `` |  |
| `ip_hash` | `bytea` | NULL | `` |  |
| `before_json` | `jsonb` | NULL | `` | منقح |
| `after_json` | `jsonb` | NULL | `` | منقح |
| `reason_code` | `varchar(80)` | NULL | `` |  |
| `metadata` | `jsonb` | NOT NULL | `{}` |  |

### `idempotency_keys` — منع تكرار أوامر API

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `scope_type` | `varchar(30)` | NOT NULL | `` |  |
| `scope_id` | `uuid` | NULL | `` |  |
| `key` | `varchar(120)` | NOT NULL | `` |  |
| `request_hash` | `char(64)` | NOT NULL | `` |  |
| `response_status` | `integer` | NULL | `` |  |
| `response_body` | `jsonb` | NULL | `` |  |
| `locked_until` | `timestamptz` | NULL | `` |  |
| `expires_at` | `timestamptz` | NOT NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `UNIQUE(scope_type,scope_id,key)`

### `outbox_events` — Transactional outbox

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `aggregate_type` | `varchar(80)` | NOT NULL | `` |  |
| `aggregate_id` | `uuid` | NOT NULL | `` |  |
| `event_type` | `varchar(120)` | NOT NULL | `` |  |
| `payload` | `jsonb` | NOT NULL | `` |  |
| `occurred_at` | `timestamptz` | NOT NULL | `now()` |  |
| `published_at` | `timestamptz` | NULL | `` |  |
| `attempt_count` | `integer` | NOT NULL | `0` |  |
| `next_attempt_at` | `timestamptz` | NULL | `` |  |

### `webhook_deliveries` — أحداث مزودي الدفع

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `provider_code` | `varchar(60)` | NOT NULL | `` |  |
| `provider_event_id` | `varchar(160)` | NOT NULL | `` |  |
| `event_type` | `varchar(120)` | NOT NULL | `` |  |
| `signature_valid` | `boolean` | NOT NULL | `` |  |
| `payload_hash` | `char(64)` | NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `received` | received/processed/ignored/failed |
| `received_at` | `timestamptz` | NOT NULL | `now()` |  |
| `processed_at` | `timestamptz` | NULL | `` |  |
| `error_code` | `varchar(80)` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(provider_code,provider_event_id)`

### `data_subject_requests` — طلبات الخصوصية

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `user_id` | `uuid` | NULL FK users | `` |  |
| `contact_phone` | `varchar(20)` | NULL | `` |  |
| `request_type` | `varchar(24)` | NOT NULL | `` | access/export/correct/delete/restrict/object |
| `status` | `varchar(24)` | NOT NULL | `submitted` | submitted/identity_verification/in_progress/fulfilled/rejected/cancelled |
| `submitted_at` | `timestamptz` | NOT NULL | `now()` |  |
| `due_at` | `timestamptz` | NULL | `` |  |
| `completed_at` | `timestamptz` | NULL | `` |  |
| `decision_reason` | `text` | NULL | `` |  |

### `legal_holds` — الحجز القانوني

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `subject_type` | `varchar(40)` | NOT NULL | `` | booking/user/payment/dispute/office |
| `subject_id` | `uuid` | NOT NULL | `` |  |
| `reason` | `text` | NOT NULL | `` |  |
| `active` | `boolean` | NOT NULL | `true` |  |
| `placed_by` | `uuid` | FK users NOT NULL | `` |  |
| `placed_at` | `timestamptz` | NOT NULL | `now()` |  |
| `released_by` | `uuid` | NULL FK users | `` |  |
| `released_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `UNIQUE(subject_type,subject_id) WHERE active=true`

### `commission_profiles` — ملفات العمولة القابلة للإصدار

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `code` | `varchar(80)` | UNIQUE NOT NULL | `` |  |
| `name_ar` | `varchar(160)` | NOT NULL | `` |  |
| `calculation_type` | `varchar(20)` | NOT NULL | `` | percentage/fixed/hybrid |
| `percentage_rate` | `numeric(9,6)` | NOT NULL | `0` |  |
| `fixed_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `currency` | `char(3)` | NULL | `` | للجزء الثابت |
| `status` | `varchar(20)` | NOT NULL | `active` | draft/active/retired |
| `effective_from` | `timestamptz` | NOT NULL | `now()` |  |
| `effective_to` | `timestamptz` | NULL | `` |  |
| `created_by` | `uuid` | FK users NOT NULL | `` |  |

**قيود إضافية:**
- `CHECK(percentage_rate>=0 AND fixed_amount>=0)`
- `CHECK(effective_to IS NULL OR effective_to>effective_from)`

### `subscription_plans` — باقات اشتراك المكاتب

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `code` | `varchar(80)` | UNIQUE NOT NULL | `` |  |
| `name_ar` | `varchar(160)` | NOT NULL | `` |  |
| `billing_period` | `varchar(20)` | NOT NULL | `` | monthly/quarterly/yearly/custom |
| `price_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `features_json` | `jsonb` | NOT NULL | `{}` |  |
| `limits_json` | `jsonb` | NOT NULL | `{}` |  |
| `status` | `varchar(20)` | NOT NULL | `active` | draft/active/retired |
| `effective_from` | `timestamptz` | NOT NULL | `now()` |  |
| `effective_to` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(price_amount>=0)`
- `CHECK(effective_to IS NULL OR effective_to>effective_from)`

### `office_subscriptions` — اشتراك مكتب في باقة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `plan_id` | `uuid` | FK subscription_plans NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `active` | trial/active/past_due/grace/suspended/cancelled/expired |
| `period_start` | `timestamptz` | NOT NULL | `` |  |
| `period_end` | `timestamptz` | NOT NULL | `` |  |
| `price_snapshot` | `jsonb` | NOT NULL | `` |  |
| `features_snapshot` | `jsonb` | NOT NULL | `{}` |  |
| `auto_renew` | `boolean` | NOT NULL | `false` |  |
| `cancel_at_period_end` | `boolean` | NOT NULL | `false` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK(period_end>period_start)`
- `UNIQUE(office_id) WHERE status IN ('trial','active','past_due','grace')`

### `subscription_invoices` — فواتير اشتراك المكتب

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `public_id` | `varchar(26)` | UNIQUE NOT NULL | `` |  |
| `office_subscription_id` | `uuid` | FK office_subscriptions NOT NULL | `` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `status` | `varchar(20)` | NOT NULL | `open` | draft/open/paid/void/uncollectible |
| `currency` | `char(3)` | NOT NULL | `` |  |
| `subtotal_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `tax_amount` | `numeric(18,2)` | NOT NULL | `0` |  |
| `total_amount` | `numeric(18,2)` | NOT NULL | `` |  |
| `due_at` | `timestamptz` | NOT NULL | `` |  |
| `paid_at` | `timestamptz` | NULL | `` |  |
| `ledger_entry_id` | `uuid` | NULL FK ledger_entries | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

**قيود إضافية:**
- `CHECK(subtotal_amount>=0 AND tax_amount>=0 AND total_amount=subtotal_amount+tax_amount)`

### `stored_files` — سجل الملفات الخاصة

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `owner_scope` | `varchar(30)` | NOT NULL | `` | platform/office/user/booking/support |
| `owner_id` | `uuid` | NULL | `` |  |
| `purpose` | `varchar(60)` | NOT NULL | `` |  |
| `object_key` | `text` | UNIQUE NOT NULL | `` |  |
| `original_filename` | `varchar(255)` | NULL | `` |  |
| `mime_type` | `varchar(120)` | NOT NULL | `` |  |
| `size_bytes` | `bigint` | NOT NULL | `` |  |
| `sha256` | `char(64)` | NOT NULL | `` |  |
| `scan_status` | `varchar(20)` | NOT NULL | `pending` | pending/clean/rejected/error |
| `retention_until` | `timestamptz` | NULL | `` |  |
| `created_by` | `uuid` | NULL FK users | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `deleted_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(size_bytes>0)`
- `UNIQUE(owner_scope,owner_id,purpose,sha256)`

### `support_attachments` — مرفقات حالات الدعم

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `case_id` | `uuid` | PK FK support_cases | `` |  |
| `file_id` | `uuid` | PK FK stored_files | `` |  |
| `uploaded_by` | `uuid` | NULL FK users | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |

### `trip_incidents` — حوادث وتوقفات الرحلات

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `trip_id` | `uuid` | FK trips NOT NULL | `` |  |
| `severity` | `varchar(12)` | NOT NULL | `` | SEV1/SEV2/SEV3 |
| `incident_type` | `varchar(60)` | NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `open` | open/contained/investigating/resolved/closed |
| `description` | `text` | NOT NULL | `` |  |
| `occurred_at` | `timestamptz` | NOT NULL | `` |  |
| `opened_by` | `uuid` | NULL FK users | `` |  |
| `resolved_at` | `timestamptz` | NULL | `` |  |
| `resolution_summary` | `text` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(severity IN ('SEV1','SEV2','SEV3'))`

### `office_violations` — مخالفات المكتب

| الحقل | النوع | القيد | الافتراضي | الوصف |
|---|---|---|---|---|
| `id` | `uuid` | PK | `gen_random_uuid()` |  |
| `office_id` | `uuid` | FK offices NOT NULL | `` |  |
| `booking_id` | `uuid` | NULL FK bookings | `` |  |
| `trip_id` | `uuid` | NULL FK trips | `` |  |
| `severity` | `varchar(16)` | NOT NULL | `` | minor/major/critical |
| `code` | `varchar(80)` | NOT NULL | `` |  |
| `status` | `varchar(24)` | NOT NULL | `open` | open/under_review/confirmed/dismissed/remediated/appealed/closed |
| `description` | `text` | NOT NULL | `` |  |
| `financial_penalty` | `numeric(18,2)` | NULL | `` |  |
| `currency` | `char(3)` | NULL | `` |  |
| `created_at` | `timestamptz` | NOT NULL | `now()` |  |
| `decided_at` | `timestamptz` | NULL | `` |  |

**قيود إضافية:**
- `CHECK(financial_penalty IS NULL OR financial_penalty>=0)`

## الفهارس الإلزامية

- `trips(route_id, scheduled_departure_at, status)` للبحث العام.
- `trip_seats(trip_id, sellable)` وخريطة فريدة للمقعد.
- `seat_holds(expires_at) WHERE status='active'` لمهمة الانتهاء.
- `bookings(office_id, created_at DESC)`, `bookings(trip_id,status)`, `bookings(contact_phone)`.
- `booking_passengers(booking_id)` و`boarding_events(trip_id,occurred_at)`.
- `payment_intents(booking_id,status)` و`payment_transactions(payment_intent_id,occurred_at)`.
- `ledger_entries(office_id,occurred_at)` و`ledger_postings(entry_id)`.
- GIN على `policy_versions.rules_json`, `configuration_values.value_json`, `audit_logs.metadata` فقط عند وجود استعلامات مثبتة.
- BRIN على الجداول الزمنية الكبيرة: `audit_logs`, `boarding_events`, `notification_deliveries`.

## قيود لا يمكن تمثيلها بـCHECK بسيط

1. **توافق جنس المقاعد:** Trigger/Domain service يقفل المقعدين المتجاورين ويمنع تخصيصًا مخالفًا إلا إذا كان الراكبان من الحجز نفسه.
2. **توازن القيد:** Deferred constraint trigger على `ledger_postings`.
3. **Snapshot:** بعد انتقال الحجز إلى `awaiting_payment` تصبح حقول السعر والسياسة immutable؛ التصحيح عبر adjustment/version وليس UPDATE صامت.
4. **No-show:** يمنع إن كانت حالة دعم P0/P1 مفتوحة أو `denied_boarding_review`.
5. **اعتماد مزدوج:** `approved_by <> created_by/requested_by` للحسابات والتسويات والاستردادات فوق الحد.
6. **عزل المستأجر:** سياسات RLS تربط المستخدم بعضوية المكتب النشطة أو دور المنصة.

## ترتيب الحذف والعلاقات

- معظم العلاقات تستخدم `ON DELETE RESTRICT`.
- الجلسات والأجهزة يمكن `ON DELETE CASCADE` عند حذف المستخدم تقنيًا، لكن المستخدم التجاري غالبًا يُخفى ولا يحذف.
- مرفقات الدعم/الوثائق تعتمد lifecycle في التخزين ولا تحذف قبل انتهاء الاحتفاظ أو Legal Hold.

## قواعد الترحيل

- كل Migration قابلة للتطبيق على بيانات قائمة، ويمنع `NOT NULL` مباشر على جدول كبير دون backfill.
- تغييرات enum تنفذ عبر قيم نصية + CHECK أو lookup tables، لا PostgreSQL ENUM المغلق.
- القيود الفريدة الكبيرة تنشأ `CONCURRENTLY` ثم تُربط إن أمكن.
