"use client";

import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type ReallocationLine = {
  passenger_id: string;
  pnr: string;
  old_seat_code: string;
  target_seat_code: string | null;
  status: string;
  conflict_code: string | null;
  score: number;
};

type ReallocationPlan = {
  id: string;
  trip_id: string;
  status: string;
  trip_version: number;
  source_inventory_version: number;
  target_inventory_version: number;
  previous_vehicle_id: string;
  target_vehicle_id: string;
  conflict_count: number;
  lines: ReallocationLine[];
  created_at: string;
  applied_at: string | null;
};

function apiError(payload: unknown): string {
  if (
    typeof payload === "object"
    && payload !== null
    && "error" in payload
    && typeof payload.error === "object"
    && payload.error !== null
    && "message" in payload.error
    && typeof payload.error.message === "string"
  ) return payload.error.message;
  return "تعذر إكمال العملية.";
}

export function ReallocationConsole() {
  const [accessToken, setAccessToken] = useStoredAccessToken();
  const [tripId, setTripId] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [version, setVersion] = useState("1");
  const [plan, setPlan] = useState<ReallocationPlan | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function mutationHeaders() {
    return {
      Authorization: `Bearer ${accessToken.trim()}`,
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    };
  }

  async function preview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken.trim() || !tripId.trim() || !vehicleId.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(
        browserApiUrl(`/v1/office/trips/${encodeURIComponent(tripId.trim())}/vehicle-change/preview`),
        {
          method: "POST",
          headers: mutationHeaders(),
          body: JSON.stringify({ target_vehicle_id: vehicleId.trim(), version: Number(version) }),
        },
      );
      const payload = await response.json() as ReallocationPlan | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("lines" in payload)) {
        setMessage(apiError(payload));
        return;
      }
      setPlan(payload as ReallocationPlan);
      setMessage("اكتملت المحاكاة دون تعديل المخزون الفعلي.");
    } catch {
      setMessage("تعذر الاتصال بخادم التشغيل.");
    } finally {
      setLoading(false);
    }
  }

  async function applyPlan() {
    if (!plan || plan.conflict_count > 0 || !accessToken.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(
        browserApiUrl(`/v1/office/trips/${encodeURIComponent(plan.trip_id)}/vehicle-change/apply`),
        {
          method: "POST",
          headers: mutationHeaders(),
          body: JSON.stringify({ plan_id: plan.id }),
        },
      );
      const payload = await response.json() as ReallocationPlan | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("status" in payload)) {
        setMessage(apiError(payload));
        return;
      }
      const applied = payload as ReallocationPlan;
      setPlan(applied);
      setVersion(String(applied.trip_version + 1));
      setMessage("تم تطبيق المخزون الجديد ذريًا وإعادة إصدار التذاكر المتأثرة.");
    } catch {
      setMessage("تعذر تطبيق خطة إعادة التوزيع.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace-grid reallocation-workspace">
      <article className="workspace-panel compact-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">محاكاة قبل التطبيق</p>
            <h2>تغيير البولمان</h2>
          </div>
          <span className="state-badge state-pending">Version check</span>
        </div>
        <form className="stack-form" onSubmit={preview}>
          <label>
            جلسة موظف المكتب
            <input type="password" value={accessToken} onChange={(event) => setAccessToken(event.target.value)} />
          </label>
          <label>
            رقم الرحلة العام
            <input value={tripId} onChange={(event) => setTripId(event.target.value)} />
          </label>
          <label>
            رقم البولمان البديل
            <input value={vehicleId} onChange={(event) => setVehicleId(event.target.value)} />
          </label>
          <label>
            نسخة الرحلة الحالية
            <input type="number" min="1" value={version} onChange={(event) => setVersion(event.target.value)} />
          </label>
          <button disabled={loading}>{loading ? "جارٍ الحساب…" : "محاكاة التوزيع"}</button>
          {message ? <p className="form-note">{message}</p> : null}
        </form>
      </article>

      <article className="workspace-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">خطة إصداريّة</p>
            <h2>نتيجة إعادة توزيع المقاعد</h2>
          </div>
          {plan ? (
            <span className={`state-badge ${plan.conflict_count ? "state-cancelled" : "state-active"}`}>
              {plan.conflict_count ? `${plan.conflict_count} تعارض` : plan.status}
            </span>
          ) : null}
        </div>
        {plan ? (
          <>
            <div className="success-grid">
              <div><span>المخزون السابق</span><strong>v{plan.source_inventory_version}</strong></div>
              <div><span>المخزون المقترح</span><strong>v{plan.target_inventory_version}</strong></div>
              <div><span>البولمان السابق</span><strong><bdi dir="ltr">{plan.previous_vehicle_id}</bdi></strong></div>
              <div><span>البولمان البديل</span><strong><bdi dir="ltr">{plan.target_vehicle_id}</bdi></strong></div>
            </div>
            <div className="data-table">
              {plan.lines.map((line) => (
                <div className="data-row reallocation-row" key={line.passenger_id}>
                  <div>
                    <strong><bdi dir="ltr">{line.pnr}</bdi></strong>
                    <small>{line.old_seat_code} ← {line.target_seat_code ?? "غير محلول"}</small>
                  </div>
                  <span className={`state-badge ${line.status === "conflict" ? "state-cancelled" : "state-active"}`}>
                    {line.conflict_code ?? line.status}
                  </span>
                  <bdi dir="ltr">{line.score}</bdi>
                </div>
              ))}
            </div>
            <div className="action-row reallocation-actions">
              <button onClick={applyPlan} disabled={loading || plan.conflict_count > 0 || plan.status === "applied"}>
                تطبيق الخطة وإعادة إصدار التذاكر
              </button>
              {plan.conflict_count > 0 ? (
                <span className="error-message">يجب حل التعارضات قبل تعديل مخزون الرحلة.</span>
              ) : null}
            </div>
          </>
        ) : (
          <div className="empty-state">
            <h3>لم تُنشأ خطة بعد</h3>
            <p>المحاكاة لا تغيّر أي مقعد، وتكشف التعارضات قبل التطبيق.</p>
          </div>
        )}
      </article>
    </section>
  );
}
