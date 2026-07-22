import { AppShell } from "@/components/app-shell";
import { SettlementConsole } from "@/components/settlement-console";

export default function PlatformFinancePage() {
  return (
    <AppShell title="العمولات والدفتر والتسويات" eyebrow="إدارة المنصة · E12">
      <section className="status-banner status-success">
        <strong>المقاصة لا تعبر العملات ولا تجمد أموالًا غير متنازع عليها</strong>
        <span>كل تصحيح مالي ينشئ قيدًا عكسيًا مستقلًا، واعتماد التسوية يتطلب مستخدمًا ثانيًا وMFA حديثًا.</span>
      </section>
      <SettlementConsole />
    </AppShell>
  );
}
