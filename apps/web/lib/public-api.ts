export type PublicLocation = {
  id: string;
  name: string;
  type: string;
  address: string | null;
};

export type TripParty = {
  id: string;
  name: string;
};

export type PolicySummary = {
  id: string;
  code: string;
  policy_type: string;
  title: string;
  summary: string;
  version_no: number;
  language: string;
};

export type PublicTrip = {
  id: string;
  office: TripParty;
  operator: TripParty;
  origin: PublicLocation;
  destination: PublicLocation;
  departure_at: string;
  arrival_at: string | null;
  currency: string;
  from_price: string;
  available_seats: number;
  payment_methods: string[];
  cancellation_summary: string;
  quote_version: number;
  policy_summaries: PolicySummary[];
};

export type SeatAvailability = {
  id: string;
  code: string;
  row: number;
  column: number;
  type: string;
  status: "available" | "held_by_you" | "unavailable" | "policy_unavailable" | "blocked";
  price: string | null;
};

export type SeatMap = {
  trip_id: string;
  layout_version: number;
  expires_at: string | null;
  seats: SeatAvailability[];
};

export type PublicPolicy = {
  id: string;
  code: string;
  version_no: number;
  language: string;
  title: string;
  content_markdown: string;
  effective_from: string;
  published_at: string | null;
  content_sha256: string;
};

const publicBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const serverBaseUrl = process.env.INTERNAL_API_BASE_URL ?? publicBaseUrl;

async function serverJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${serverBaseUrl}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function browserApiUrl(path: string): string {
  return `${publicBaseUrl}${path}`;
}

export async function getPublicLocations(): Promise<PublicLocation[]> {
  return (await serverJson<PublicLocation[]>("/v1/public/locations")) ?? [];
}

export async function searchTrips(params: {
  originId: string;
  destinationId: string;
  date: string;
  passengers: number;
}): Promise<PublicTrip[]> {
  const query = new URLSearchParams({
    origin_id: params.originId,
    destination_id: params.destinationId,
    date: params.date,
    passengers: String(params.passengers),
  });
  return (await serverJson<PublicTrip[]>(`/v1/public/trips/search?${query}`)) ?? [];
}

export async function getPublicTrip(tripId: string): Promise<PublicTrip | null> {
  return serverJson<PublicTrip>(`/v1/public/trips/${encodeURIComponent(tripId)}`);
}

export async function getPublicSeatMap(tripId: string): Promise<SeatMap | null> {
  return serverJson<SeatMap>(`/v1/public/trips/${encodeURIComponent(tripId)}/seats`);
}

export async function getPublicPolicy(code: string, officeId?: string): Promise<PublicPolicy | null> {
  const query = new URLSearchParams({ language: "ar" });
  if (officeId) query.set("office_id", officeId);
  return serverJson<PublicPolicy>(`/v1/public/policies/${encodeURIComponent(code)}?${query}`);
}
