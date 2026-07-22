import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const controls = [
  ["قائمة الاستردادات", "GET /v1/platform/refunds", "حسب الحالة والمكتب"],
  ["قائمة اعتراضات الدفع", "GET /v1/platform/chargebacks", "حسب الحالة والموعد النهائي"],
  ["فصل الصلاحيات", "platform.refund.view", "عرض مركزي دون تجاوز عزل المكتب في مساراته"],
  ["أثر مالي", "Ledger + Commission", "عكس منضبط دون حذف أو تعديل تاريخي"],
];

export default function PlatformRefundsPage() {
  return (
    <AppShell title="رقابة الاستردادات والاعتراضات" eyebrow="إدارة المنصة · E09">
      <section className="admin-layout">
        <article className="metric-card">
          <span>قاعدة التعويض</span>
          <strong className="metric-number">1×</strong>
          <p>لا يجمع الحجز بين استرداد مفتوح وتعويض Chargeback عن المبلغ نفسه.</p>
        </article>
        <div className="control-list">
          {controls.map(([title, endpoint, description]) => (
            <div className="control-row expanded-control" key={title}>
              <span className="control-check" aria-hidden="true">✓</span>
              <div>
                <strong>{title}</strong>
                <small>{description}</small>
              </div>
              <bdi dir="ltr">{endpoint}</bdi>
            </div>
          ))}
        </div>
      </section>
      <div className="card-footer">
        <Link className="text-link" href="/platform">العودة إلى مركز التحكم</Link>
        <Link className="text-link" href="/office/refunds">مسار المكتب</Link>
      </div>
    </AppShell>
  );
}
