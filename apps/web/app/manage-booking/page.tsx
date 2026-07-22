import { AppShell } from "@/components/app-shell";
import { BookingManager } from "@/components/booking-manager";

export default async function ManageBookingPage({
  searchParams,
}: {
  searchParams: Promise<{ pnr?: string }>;
}) {
  const params = await searchParams;
  return (
    <AppShell title="استرجاع الحجز والتذاكر" eyebrow="الخدمة الذاتية">
      <BookingManager initialPnr={params.pnr ?? ""} />
    </AppShell>
  );
}
