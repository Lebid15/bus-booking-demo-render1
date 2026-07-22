import { AppShell } from "@/components/app-shell";
import { BoardingConsole } from "@/components/boarding-console";

export default function OfficeBoardingPage() {
  return (
    <AppShell title="الصعود وقائمة الركاب" eyebrow="لوحة المكتب · E10">
      <section className="status-banner status-success">
        <strong>QR أحادي الاستخدام وManifest غير قابل للتعديل بصمت</strong>
        <span>المزامنة دون اتصال مقيدة بجهاز موثوق وحزمة مشفرة وموقعة ومحدودة المدة.</span>
      </section>
      <BoardingConsole />
    </AppShell>
  );
}
