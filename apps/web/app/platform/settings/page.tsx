import { AppShell } from "@/components/app-shell";
import { ConfigurationConsole } from "@/components/configuration-console";

export default function PlatformSettingsPage() {
  return <AppShell title="إعدادات المنصة" eyebrow="إدارة المنصة · E13"><section className="status-banner status-success"><strong>فصل الواجبات مفروض</strong><span>التغيير الحساس يُقترح أولًا ثم يعتمده مستخدم منصة ثانٍ مع MFA حديث.</span></section><ConfigurationConsole scope="platform" /></AppShell>;
}
