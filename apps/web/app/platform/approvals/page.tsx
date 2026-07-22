import { ApprovalConsole } from "@/components/approval-console";
import { AppShell } from "@/components/app-shell";

export default function PlatformApprovalsPage() {
  return (
    <AppShell title="الاعتماد المزدوج" eyebrow="إدارة المنصة · E16">
      <section className="status-banner status-success">
        <strong>فصل المنشئ عن المعتمد</strong>
        <span>تعليق المكتب أو إنهاؤه لا ينفذ قبل MFA حديث ومراجعة مستخدم منصة ثانٍ.</span>
      </section>
      <ApprovalConsole />
    </AppShell>
  );
}
