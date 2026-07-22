import { AppShell } from "@/components/app-shell";
import { SupportConsole } from "@/components/support-console";

export default function OfficeSupportPage() {
  return (
    <AppShell title="الدعم واستمرارية التشغيل" eyebrow="لوحة المكتب · E11">
      <section className="status-banner status-success">
        <strong>رفض تذكرة صحيحة يفتح P1 تلقائيًا</strong>
        <span>يُجمّد المقعد، ويبدأ SLA، ويبقى التحقق الاحتياطي متاحًا دون تحصيل دفعة جديدة.</span>
      </section>
      <SupportConsole />
    </AppShell>
  );
}
