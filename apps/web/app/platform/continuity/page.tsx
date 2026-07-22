import { AppShell } from "@/components/app-shell";
import { ContinuityConsole } from "@/components/continuity-console";

export default function ContinuityPage() {
  return <AppShell title="الاستمرارية والإطلاق" eyebrow="إدارة المنصة · E18">
    <section className="status-banner status-success"><strong>إعادة الفتح محكومة بالمصالحة</strong><span>لا تعود الكتابات التجارية قبل سلامة المقاعد والمدفوعات والدفتر.</span></section>
    <ContinuityConsole />
  </AppShell>;
}
