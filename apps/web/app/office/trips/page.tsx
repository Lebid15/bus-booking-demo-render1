import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const lifecycle = [
  ["مسودة", "تجميع المسار والمركبة والسائق والأسعار والسياسات"],
  ["مجدولة", "تم تجميد Snapshot السياسات والأسعار وإنشاء مخزون المقاعد"],
  ["منشورة", "ظاهرة للعامة دون بيع قبل موعد فتح الحجز"],
  ["مفتوحة للحجز", "المخزون صالح والشراء متاح"],
  ["الصعود", "فتح ثم إغلاق الصعود مع حراس الحالات العاجلة"],
  ["انطلقت", "لا انتقال قبل توازن الركاب والمقاعد"],
];

const readiness = [
  "مكتب وفرع وناقل بحالة تشغيلية صالحة",
  "مركبة وسائق بوثائق نافذة ودون تعارض زمني",
  "مخطط مقاعد منشور ومتطابق مع عدد المقاعد",
  "سعر وعملة ونوافذ حجز وصعود صحيحة",
  "سياسات الإلغاء والدفع والصعود بإصدارات نافذة",
];

export default function OfficeTripsPage() {
  return (
    <AppShell title="الرحلات والجدولة" eyebrow="لوحة المكتب · التشغيل">
      <section className="stat-grid">
        <article className="metric-card">
          <span>حالات دورة الرحلة</span>
          <strong className="metric-number">11</strong>
          <p>من المسودة حتى الإكمال أو الإلغاء أو التوقف.</p>
        </article>
        <article className="metric-card">
          <span>حراس الجاهزية</span>
          <strong className="metric-number">5</strong>
          <p>لا جدولة دون موارد وسياسات وسعر صالح.</p>
        </article>
        <article className="metric-card">
          <span>مصدر المقاعد</span>
          <strong className="metric-number">1</strong>
          <p>TripSeat هو المخزون الموحد لكل رحلة.</p>
        </article>
      </section>

      <section className="workspace-grid">
        <article className="workspace-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">دورة تشغيل محكومة</p>
              <h2>من المسودة إلى فتح الحجز</h2>
            </div>
            <span className="state-badge state-active">E04 منفذة</span>
          </div>
          <div className="timeline-list">
            {lifecycle.map(([title, description], index) => (
              <div className="timeline-row" key={title}>
                <span className="timeline-dot" aria-hidden="true" />
                <div>
                  <strong>{title}</strong>
                  <small>{description}</small>
                </div>
                <span>{String(index + 1).padStart(2, "0")}</span>
              </div>
            ))}
          </div>
        </article>

        <aside className="workspace-panel compact-panel">
          <p className="eyebrow">Readiness Check</p>
          <h2>ما الذي يمنع الجدولة؟</h2>
          <div className="security-stack">
            {readiness.map((item) => <span key={item}>✓ {item}</span>)}
          </div>
          <p className="form-note">
            عند النقص يعيد الخادم TRIP_NOT_READY مع الحقول والأسباب بدل تغيير الحالة جزئيًا.
          </p>
          <div className="card-footer">
            <Link className="text-link" href="/office/fleet">الأسطول</Link>
            <Link className="text-link" href="/office">لوحة المكتب</Link>
          </div>
        </aside>
      </section>
    </AppShell>
  );
}
