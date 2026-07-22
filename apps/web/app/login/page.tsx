import { AppShell } from "@/components/app-shell";
import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  return (
    <AppShell title="تسجيل الدخول" eyebrow="الهوية والجلسات">
      <section className="status-banner status-success">
        <strong>النسخة التجريبية جاهزة</strong>
        <span>اختر حسابًا تجريبيًا ثم افتح لوحة المكتب أو مركز إدارة المنصة.</span>
      </section>
      <LoginForm />
    </AppShell>
  );
}
