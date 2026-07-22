import { AppShell } from "@/components/app-shell";
import { PlatformSubscriptionConsole } from "@/components/subscription-console";

export default function PlatformSubscriptionsPage() {
  return (
    <AppShell title="الباقات واشتراكات المكاتب" eyebrow="إدارة المنصة · E17">
      <section className="status-banner status-success">
        <strong>الاشتراك مستقل عن عمولة الحجز</strong>
        <span>تغيير سعر الباقة لا يعيد كتابة الفترات المدفوعة، وكل فاتورة وقبض ينعكسان في Ledger بقيود متوازنة.</span>
      </section>
      <PlatformSubscriptionConsole />
    </AppShell>
  );
}
