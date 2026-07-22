import { AppShell } from "@/components/app-shell";
import { OfficeSettlementViewer } from "@/components/settlement-console";

export default function OfficeSettlementsPage() {
  return (
    <AppShell title="كشف العمولات والتسويات" eyebrow="لوحة المكتب · E12">
      <section className="status-banner status-success">
        <strong>كل عملة مستقلة وكل بند متنازع عليه ظاهر</strong>
        <span>يمكن للمكتب مراجعة صافي مستحقاته والعمولات والمبالغ المجمدة دون الوصول إلى حسابات مكاتب أخرى.</span>
      </section>
      <OfficeSettlementViewer />
    </AppShell>
  );
}
