import { AppShell } from "@/components/app-shell";
import { OfficeSubscriptionConsole } from "@/components/subscription-console";

export default function OfficeSubscriptionPage() {
  return (
    <AppShell title="اشتراك المكتب" eyebrow="لوحة المكتب · E17">
      <section className="status-banner status-success">
        <strong>الخطة والسعر والفترة مثبتة لكل دورة</strong>
        <span>انتهاء الاشتراك يوقف العمليات التجارية الجديدة تدريجيًا، ولا يلغي الحجوزات أو التذاكر أو الحقوق المالية القائمة.</span>
      </section>
      <OfficeSubscriptionConsole />
    </AppShell>
  );
}
