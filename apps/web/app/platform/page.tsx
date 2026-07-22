import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const controls = [
  ["اعتماد المكاتب والوثائق", "دورة مراجعة مع اعتماد مزدوج للملفات المعززة", "/office/verification", "منفذ"],
  ["إدارة المواقع والخطوط", "كتالوج اتجاهي للمواقع والمسارات", "/platform/catalog", "منفذ"],
  ["الأسطول ومخططات المقاعد", "إصدارات مستقلة وحراس وثائق", "/office/fleet", "منفذ"],
  ["إدارة السياسات والإعدادات", "قواعد المنصة وإصداراتها", "/platform/policies", "منفذ"],
  ["إعدادات المنصة", "إصدارات القيم والموافقات المزدوجة وسجل before/after", "/platform/settings", "منفذ"],
  ["التسويات والدفتر المالي", "المقاصة حسب العملة والموافقات المزدوجة والقيود العكسية", "/platform/finance", "منفذ"],
  ["الاعتماد المزدوج", "طلبات التعليق والإنهاء الحساسة مع فصل المنشئ عن المعتمد", "/platform/approvals", "منفذ"],
  ["النزاعات والقرارات", "تسبيب القرار والأثر المالي ونافذة الاعتراض والمراجعة المستقلة", "/platform/disputes", "منفذ"],
  ["الاستردادات واعتراضات الدفع", "المراجعة والتنفيذ ومنع التعويض المزدوج", "/platform/refunds", "منفذ"],
  ["الدعم والنزاعات والمخالفات", "حالات P1 والتصعيد وحقوق الرحلات المتوقفة", "/platform/incidents", "منفذ"],
  ["تشغيل الإشعارات", "القوالب والقنوات وإعادة المحاولة والتصعيد", "/platform/notifications", "منفذ"],
  ["الأمان والخصوصية", "المخاطر وLegal Hold وعزل الملفات وتدقيق الأسرار", "/platform/security", "منفذ"],
  ["الاشتراكات والباقات", "الخطط والفواتير وحدود الاستخدام وتاريخ النفاذ", "/platform/subscriptions", "منفذ"],
];

export default function PlatformPage() {
  return (
    <AppShell title="مركز تحكم المنصة" eyebrow="إدارة المنصة">
      <section className="admin-layout">
        <article className="metric-card">
          <span>Gate الحالية</span>
          <strong>G16</strong>
          <p>Subscriptions, Billing &amp; Usage Entitlements</p>
        </article>
        <div className="control-list">
          {controls.map(([control, description, href, state]) => (
            <div className="control-row expanded-control" key={control}>
              <span className="control-check" aria-hidden="true">✓</span>
              <div>
                <strong>{control}</strong>
                <small>{description}</small>
              </div>
              {href !== "#" ? <Link href={href}>{state}</Link> : <span className="module-state">{state}</span>}
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
