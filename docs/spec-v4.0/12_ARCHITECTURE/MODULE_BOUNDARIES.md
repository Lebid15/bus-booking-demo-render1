# حدود الوحدات

| الوحدة | تملك | لا تملك مباشرة |
|---|---|---|
| inventory | seat holds, availability, assignments | الدفع والدفتر |
| bookings | booking/passenger snapshots | تعديل مخطط المركبة |
| payments | payment intents/transactions/provider events | تغيير المقعد |
| finance | ledger, commission, settlement | قرار الصعود |
| boarding | tickets, scans, manifest events | تعديل السعر |
| policies | versions, consent, evaluation | حذف Snapshot |
| support | cases, messages, resolutions | ترحيل Ledger بلا حدث مالي |
| notifications | delivery attempts | تغيير حالة الحجز |

## قواعد التبعية

- الوحدات تتواصل عبر خدمات تطبيقية وأحداث مجال، لا Imports عشوائية للModels.
- finance يقرأ Snapshots/Events ولا يعيد حساب التاريخ من إعداد حالي.
- notifications مستهلك للحدث، وفشله لا يرجع المعاملة التجارية.
