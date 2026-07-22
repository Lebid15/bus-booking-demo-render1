import { AppShell } from "@/components/app-shell";
import { DisputeConsole } from "@/components/dispute-console";

export default function PlatformDisputesPage() {
  return (
    <AppShell title="النزاعات والقرارات المالية" eyebrow="إدارة المنصة · E16">
      <section className="status-banner status-success">
        <strong>الدعم لا يساوي المال</strong>
        <span>إصدار أثر مالي يتطلب صلاحية مالية مستقلة، وكل قرار مسبب وقابل للاعتراض ضمن نافذته.</span>
      </section>
      <DisputeConsole scope="platform" />
    </AppShell>
  );
}
