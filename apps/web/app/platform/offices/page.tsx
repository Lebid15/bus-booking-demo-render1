import { PlatformOfficeAdminConsole } from "@/components/admin-reporting-console";
import { AppShell } from "@/components/app-shell";

export default function PlatformOfficesPage() {
  return (
    <AppShell title="إدارة المكاتب" eyebrow="إدارة المنصة · E16">
      <section className="status-banner status-success">
        <strong>التعليق لا يلغي الحقوق القائمة</strong>
        <span>يوقف الحجوزات الجديدة فقط، بينما تبقى الحجوزات والتذاكر والتسويات السابقة قابلة للمعالجة.</span>
      </section>
      <PlatformOfficeAdminConsole />
    </AppShell>
  );
}
