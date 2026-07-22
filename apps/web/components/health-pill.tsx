import { getApiHealth } from "@/lib/api";

export async function HealthPill() {
  const health = await getApiHealth();
  const ready = health?.status === "ok";
  return (
    <span className={`health-pill ${ready ? "ready" : "offline"}`} aria-live="polite">
      <span aria-hidden="true" className="health-dot" />
      {ready ? "الخدمة متصلة" : "الخدمة غير متاحة"}
    </span>
  );
}
