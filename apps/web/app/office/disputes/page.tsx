import { AppShell } from "@/components/app-shell";
import { DisputeConsole } from "@/components/dispute-console";

export default function OfficeDisputesPage() {
  return (
    <AppShell title="نزاعات المكتب والاعتراضات" eyebrow="لوحة المكتب · E16">
      <DisputeConsole scope="office" />
    </AppShell>
  );
}
