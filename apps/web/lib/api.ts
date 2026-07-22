export type ApiHealth = {
  status: "ok" | "degraded";
  service?: string;
  checks?: Record<string, string>;
};

const publicBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const serverBaseUrl = process.env.INTERNAL_API_BASE_URL ?? publicBaseUrl;

export async function getApiHealth(): Promise<ApiHealth | null> {
  try {
    const response = await fetch(`${serverBaseUrl}/health/live`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1500),
    });
    if (!response.ok) return null;
    return (await response.json()) as ApiHealth;
  } catch {
    return null;
  }
}

export function apiUrl(path: string): string {
  return `${publicBaseUrl}${path}`;
}
