import { AppShell } from "@/components/app-shell";
import { ConfigurationConsole } from "@/components/configuration-console";

export default function OfficeSettingsPage() {
  return <AppShell title="إعدادات المكتب" eyebrow="لوحة المكتب · E13"><section className="status-banner status-success"><strong>قيم محكومة ضمن حدود المنصة</strong><span>كل تغيير يحفظ كإصدار جديد مع السبب والقيمة السابقة وتاريخ النفاذ.</span></section><ConfigurationConsole scope="office" /></AppShell>;
}
