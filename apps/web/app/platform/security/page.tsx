import { AppShell } from "@/components/app-shell";
import { PlatformSecurityConsole } from "@/components/security-console";

export default function PlatformSecurityPage() {
  return <AppShell title="الأمان والخصوصية ومكافحة الاحتيال" eyebrow="إدارة المنصة · E14"><PlatformSecurityConsole /></AppShell>;
}
