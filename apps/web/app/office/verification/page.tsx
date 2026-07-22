import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const verificationSteps = [
  ["بيانات المكتب", "مكتملة", "legal_name · trade_name · support_phone"],
  ["السجل التجاري", "بانتظار المراجعة", "commercial_registration"],
  ["رخصة التشغيل", "بانتظار المراجعة", "operating_license"],
  ["هوية الممثل", "بانتظار المراجعة", "representative_identity"],
];

export default function OfficeVerificationPage() {
  return (
    <AppShell title="اعتماد المكتب والوثائق" eyebrow="لوحة المكتب · التحقق">
      <section className="workspace-grid">
        <article className="workspace-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">حالة الطلب</p>
              <h2>مسودة قابلة للإرسال بعد اكتمال الملف</h2>
            </div>
            <span className="state-badge state-pending">draft</span>
          </div>
          <div className="timeline-list">
            {verificationSteps.map(([title, state, code]) => (
              <div className="timeline-row" key={code}>
                <span className="timeline-dot" aria-hidden="true" />
                <div>
                  <strong>{title}</strong>
                  <small>{code}</small>
                </div>
                <span>{state}</span>
              </div>
            ))}
          </div>
          <button type="button">إرسال ملف الاعتماد</button>
          <p className="form-note">
            يتحقق الخادم من جميع الوثائق المطلوبة قبل الانتقال إلى submitted، ولا يمكن تجاوز النواقص من الواجهة.
          </p>
        </article>

        <aside className="workspace-panel compact-panel">
          <p className="eyebrow">حماية التغييرات المالية</p>
          <h2>حساب التسوية</h2>
          <p>أي تغيير جديد يحتاج MFA حديثًا، واعتماد مستخدم ثانٍ، وفترة تهدئة قبل النفاذ.</p>
          <div className="security-stack">
            <span>✓ لا تُعرض بيانات الحساب الكاملة</span>
            <span>✓ إشعار للحساب السابق</span>
            <span>✓ سجل تدقيق وOutbox</span>
          </div>
          <Link className="text-link" href="/office">العودة إلى لوحة المكتب</Link>
        </aside>
      </section>
    </AppShell>
  );
}
