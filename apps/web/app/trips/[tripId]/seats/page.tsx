import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { SeatHoldClient } from "@/components/seat-hold-client";
import { getPublicSeatMap, getPublicTrip } from "@/lib/public-api";

type SeatPageProps = {
  params: Promise<{ tripId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function SeatPage({ params, searchParams }: SeatPageProps) {
  const { tripId } = await params;
  const raw = await searchParams;
  const value = Array.isArray(raw.passengers) ? raw.passengers[0] : raw.passengers;
  const passengerCount = Math.min(8, Math.max(1, Number(value) || 1));
  const [trip, seatMap] = await Promise.all([getPublicTrip(tripId), getPublicSeatMap(tripId)]);
  if (!trip || !seatMap) notFound();

  return (
    <AppShell title="اختيار المقاعد" eyebrow={`${trip.origin.name} ← ${trip.destination.name}`}>
      <SeatHoldClient trip={trip} initialSeatMap={seatMap} passengerCount={passengerCount} />
    </AppShell>
  );
}
