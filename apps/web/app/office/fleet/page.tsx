import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const fleetCards = [
  ["مخططات المقاعد", "2", "إصدارات مستقلة غير قابلة للتعديل الرجعي"],
  ["المركبات النشطة", "0", "لن تقبل الجدولة قبل اكتمال الوثائق"],
  ["السائقون الجاهزون", "0", "الترخيص والحالة يتحقق منهما الخادم"],
];

export default function OfficeFleetPage() {
  return (
    <AppShell title="الأسطول ومخططات المقاعد" eyebrow="لوحة المكتب · الأسطول">
      <section className="stat-grid">
        {fleetCards.map(([label, value, note]) => (
          <article className="metric-card" key={label}>
            <span>{label}</span>
            <strong className="metric-number">{value}</strong>
            <p>{note}</p>
          </article>
        ))}
      </section>

      <section className="workspace-panel table-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">مخطط نشط</p>
            <h2>بولمان 2+2 · الإصدار 1</h2>
          </div>
          <button type="button">إنشاء إصدار جديد</button>
        </div>
        <div className="seat-preview" aria-label="معاينة مخطط المقاعد">
          {["1A", "1B", "1C", "1D", "2A", "2B", "2C", "2D"].map((seat) => (
            <span key={seat}>{seat}</span>
          ))}
        </div>
        <p className="form-note">
          المقاعد المتجاورة تُعرّف صراحة، والمقعدان عبر الممر لا يُعاملان كوحدة واحدة.
        </p>
        <Link className="text-link" href="/office">العودة إلى لوحة المكتب</Link>
      </section>
    </AppShell>
  );
}
