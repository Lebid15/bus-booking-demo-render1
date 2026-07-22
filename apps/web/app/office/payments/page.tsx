import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const checks = [
  "مطابقة مرجع التحويل والمبلغ والعملة",
  "اعتماد وقت التحويل الفعلي لا وقت رفع الصورة",
  "منع المرجع أو الإثبات المكرر",
  "عدم إعادة المقعد المباع عند وصول دفع متأخر",
  "قيد مالي متوازن وسجل تدقيق لكل اعتماد",
];

export default function OfficePaymentsPage() {
  return (
    <AppShell title="المدفوعات والتحويلات" eyebrow="لوحة المكتب · المالية">
      <section className="stat-grid">
        <article className="metric-card">
          <span>قنوات الإصدار الأول</span>
          <strong className="metric-number">3</strong>
          <p>نقد المكتب، التحويل اليدوي، وبنية دفع إلكتروني قابلة للتفعيل.</p>
        </article>
        <article className="metric-card">
          <span>مصدر الحقيقة</span>
          <strong className="metric-number">1</strong>
          <p>PaymentTransaction مع Ledger append-only ودون تعديل تاريخي.</p>
        </article>
        <article className="metric-card">
          <span>حماية التكرار</span>
          <strong className="metric-number">100%</strong>
          <p>المفاتيح والأحداث ومراجع التحويل فريدة وقابلة لإعادة المحاولة بأمان.</p>
        </article>
      </section>
      <section className="workspace-grid">
        <article className="workspace-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">قائمة التحقق</p>
              <h2>مراجعة التحويل قبل الاعتماد</h2>
            </div>
            <span className="state-badge state-active">E07 منفذة</span>
          </div>
          <div className="timeline-list">
            {checks.map((item, index) => (
              <div className="timeline-row" key={item}>
                <span className="timeline-dot" aria-hidden="true" />
                <strong>{item}</strong>
                <span>{String(index + 1).padStart(2, "0")}</span>
              </div>
            ))}
          </div>
        </article>
        <aside className="workspace-panel compact-panel">
          <p className="eyebrow">واجهات التشغيل</p>
          <h2>المسارات الخادمية</h2>
          <div className="security-stack">
            <span>✓ قائمة التحويلات المرسلة</span>
            <span>✓ قبول أو رفض مع سبب</span>
            <span>✓ تسجيل قبض المكتب بإيصال</span>
            <span>✓ Webhook موقّع ومصالحات</span>
          </div>
          <p className="form-note">عرض البيانات الحية يتطلب جلسة مكتب وصلاحية مالية؛ لا يقبل الخادم office_id من العميل.</p>
          <div className="card-footer">
            <Link className="text-link" href="/office">العودة إلى اللوحة</Link>
            <Link className="text-link" href="/manage-booking">تجربة خدمة الزبون</Link>
          </div>
        </aside>
      </section>
    </AppShell>
  );
}
