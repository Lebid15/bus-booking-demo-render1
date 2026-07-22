import { AppShell } from "@/components/app-shell";
import { UserPrivacyConsole } from "@/components/security-console";

export default function PrivacyPage() {
  return <AppShell title="الخصوصية وحقوق البيانات" eyebrow="الحساب · E14"><UserPrivacyConsole /></AppShell>;
}
