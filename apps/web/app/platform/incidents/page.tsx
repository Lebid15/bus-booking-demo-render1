import { AppShell } from "@/components/app-shell";
import { IncidentConsole } from "@/components/incident-console";

export default function PlatformIncidentsPage() {
  return (
    <AppShell title="الحوادث والتصعيد وحقوق المسافرين" eyebrow="إدارة المنصة · E11">
      <section className="status-banner status-success">
        <strong>لا إغلاق لرحلة متوقفة قبل معالجة كل حجز</strong>
        <span>التصعيد الآلي يثبت مخالفة المكتب عند تجاوز SLA ويُبقي جميع القرارات قابلة للتدقيق.</span>
      </section>
      <IncidentConsole />
    </AppShell>
  );
}
