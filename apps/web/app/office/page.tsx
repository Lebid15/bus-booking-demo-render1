import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const modules = [
  ["اعتماد المكتب", "الوثائق، دورة المراجعة، وحساب التسوية المحمي", "/office/verification", "منفذ"],
  ["الأسطول", "المركبات والسائقون ومخططات المقاعد ذات الإصدارات", "/office/fleet", "منفذ"],
  ["الرحلات", "إدارة الجداول والنشر والجاهزية", "/office/trips", "منفذ"],
  ["خريطة المقاعد", "التوفر الحي والحجوزات المؤقتة", "/office/trips", "نواة منفذة"],
  ["الحجوزات", "إنشاء الحجز ومتابعة الدفع والتذاكر", "/manage-booking", "منفذ"],
  ["المدفوعات", "النقد والتحويل والمصالحة والدفتر المالي", "/office/payments", "منفذ"],
  ["التسويات", "كشف صافي المستحقات والعمولات والمبالغ المجمدة حسب العملة", "/office/settlements", "منفذ"],
  ["التعديلات والاستردادات", "إلغاء جزئي وتغيير راكب أو مقعد ومسار استرداد محكوم", "/office/refunds", "منفذ"],
  ["الصعود", "Manifest ومسح QR والعمل دون اتصال", "/office/boarding", "منفذ"],
  ["تغيير البولمان", "محاكاة إعادة توزيع المقاعد وتطبيق مخزون إصداري", "/office/reallocation", "منفذ"],
  ["الدعم والحوادث", "P1 وSLA والتحقق الاحتياطي عند التعطل", "/office/support", "منفذ"],
  ["النزاعات والاعتراضات", "رد المكتب بالأدلة وحق اعتراض واحد ضمن النافذة النظامية", "/office/disputes", "منفذ"],
  ["إعدادات المكتب", "قيم محكومة بإصدارات وسجل تدقيق ضمن حدود المنصة", "/office/settings", "منفذ"],
  ["الإشعارات", "صندوق المكتب ومحاولات التواصل التشغيلية", "/office/notifications", "منفذ"],
  ["الاشتراك", "الخطة والاستخدام والفواتير وطلبات التغيير", "/office/subscription", "منفذ"],
];

export default function OfficePage() {
  return (
    <AppShell title="مساحة تشغيل المكتب" eyebrow="لوحة المكتب">
      <section className="status-banner status-success">
        <strong>Gate G16 قيد الإغلاق</strong>
        <span>أصبحت النزاعات ذات دورة قرار واعتراض مستقلة، والتقارير المالية تُشتق من Ledger، وتعليق المكتب يحفظ حقوق الحجوزات القائمة.</span>
      </section>
      <section className="module-grid">
        {modules.map(([title, description, href, state]) => (
          <article className="module-card" key={title}>
            <span className="module-icon" aria-hidden="true">•</span>
            <h2>{title}</h2>
            <p>{description}</p>
            <div className="card-footer">
              <span className="module-state">{state}</span>
              {href !== "#" ? <Link href={href}>فتح الوحدة</Link> : <span className="muted-link">قريبًا</span>}
            </div>
          </article>
        ))}
      </section>
    </AppShell>
  );
}
