import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { PolicyPublisher } from "@/components/policy-publisher";

const policyTypes = [
  ["الإلغاء", "cancellation", "تُحفظ قواعدها الآلية ومحتواها وبصمتها"],
  ["الدفع", "payment", "تحدد الطرق والمهل والقيود النافذة"],
  ["الصعود", "boarding", "تضبط نوافذ الصعود وعدم الحضور"],
  ["الأمتعة", "baggage", "نسخة مستقلة قابلة للإسناد لاحقًا"],
];

export default function PlatformPoliciesPage() {
  return (
    <AppShell title="إصدارات السياسات" eyebrow="إدارة المنصة · الحوكمة">
      <section className="status-banner status-success">
        <strong>السياسة لا تُعدّل بصمت</strong>
        <span>كل تغيير ينشئ إصدارًا جديدًا ببصمة SHA-256 وفترة نفاذ محددة.</span>
      </section>
      <section className="module-grid">
        {policyTypes.map(([title, code, description]) => (
          <article className="module-card" key={code}>
            <span className="module-state">{code}</span>
            <h2>{title}</h2>
            <p>{description}</p>
          </article>
        ))}
      </section>
      <section className="workspace-panel table-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Snapshot at scheduling</p>
            <h2>الرحلة تحتفظ بالإصدار الذي جُدولت عليه</h2>
          </div>
          <Link className="text-link" href="/platform">العودة إلى الإدارة</Link>
        </div>
        <p>
          أي حجز لاحق يرث Snapshot الرحلة، لذلك لا تؤثر سياسة جديدة على رحلة أو حجز قائم بأثر رجعي.
        </p>
      </section>
      <PolicyPublisher />
    </AppShell>
  );
}
