# تتبع أحداث المنتج

## مبادئ

- لا يرسل الاسم أو الهاتف أو رقم الهوية أو PNR الخام إلى أدوات التحليل.
- يستخدم session/user pseudonymous IDs.
- يتم Consent للأدوات غير الضرورية.

## أحداث رئيسية

search_submitted، trip_viewed، seat_hold_created، seat_selected، passenger_form_error، booking_reviewed، payment_method_selected، booking_created، payment_confirmed، ticket_downloaded، cancellation_quote_viewed، support_case_created.

## خصائص آمنة

surface، locale، route_id داخلي غير حساس، office_id مستعار للتحليل الداخلي، payment_method_type، error_code، latency_bucket، device_class.
