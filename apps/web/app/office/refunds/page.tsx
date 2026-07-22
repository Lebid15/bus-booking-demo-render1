import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const workflow = [
  ["requested", "طلب جديد", "تثبيت المبلغ من Quote الحجز وسجل الراكب"],
  ["under_review", "تحت المراجعة", "فحص الدفع الأصلي وعدم وجود Chargeback مفتوح"],
  ["approved", "معتمد", "اعتماد مستخدم ثانٍ وMFA للمبالغ الحساسة"],
  ["processing", "قيد التنفيذ", "إرسال أمر الاسترداد للمزود أو صندوق المكتب"],
  ["succeeded", "مكتمل", "عكس القيود وتحديث حالة الدفع والحجز"],
];

export default function OfficeRefundsPage() {
  return (
    <AppShell title="الاستردادات وتعديلات الحجز" eyebrow="لوحة المكتب · E09">
      <section className="status-banner status-success">
        <strong>مسار استرداد محكوم</strong>
        <span>لا يمكن لمن طلب الاسترداد اعتماد طلبه، ولا يُصرف المبلغ مرتين عند وجود اعتراض دفع.</span>
      </section>
      <section className="workspace-grid">
        <article className="workspace-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">دورة المعالجة</p>
              <h2>من الطلب حتى إغلاق القيد المالي</h2>
            </div>
            <span className="state-badge state-active">Append-only</span>
          </div>
          <div className="timeline-list">
            {workflow.map(([state, label, description]) => (
              <div className="timeline-row" key={state}>
                <span className="timeline-dot" aria-hidden="true" />
                <div>
                  <strong>{label}</strong>
                  <small>{description}</small>
                </div>
                <bdi dir="ltr">{state}</bdi>
              </div>
            ))}
          </div>
        </article>
        <aside className="workspace-panel compact-panel">
          <p className="eyebrow">الحراس المنفذة</p>
          <h2>قبل الاعتماد</h2>
          <div className="security-stack">
            <span>✓ سقف المبلغ المتاح للاسترداد</span>
            <span>✓ منع اعتماد منشئ الطلب</span>
            <span>✓ MFA حديث للمبالغ الحساسة</span>
            <span>✓ منع التعويض مع Chargeback مفتوح</span>
            <span>✓ قيدان متوازنان عند الاعتماد والصرف</span>
          </div>
          <div className="card-footer">
            <Link className="text-link" href="/office/payments">المدفوعات</Link>
            <Link className="text-link" href="/office">لوحة المكتب</Link>
          </div>
        </aside>
      </section>
    </AppShell>
  );
}
