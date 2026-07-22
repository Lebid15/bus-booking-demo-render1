import { AppShell } from "@/components/app-shell";
import { ReallocationConsole } from "@/components/reallocation-console";

export default function OfficeReallocationPage() {
  return (
    <AppShell title="تغيير البولمان وإعادة توزيع المقاعد" eyebrow="لوحة المكتب · E11">
      <section className="status-banner status-success">
        <strong>محاكاة أولًا، ثم تطبيق ذري</strong>
        <span>تُحفظ المجموعات المحمية وقاعدة الجنس ويُمنع المقعد المزدوج قبل إصدار التذاكر الجديدة.</span>
      </section>
      <ReallocationConsole />
    </AppShell>
  );
}
