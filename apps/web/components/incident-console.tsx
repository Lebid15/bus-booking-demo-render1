"use client";

import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type SupportCase = { id: string; priority: string; category: string; status: string; booking_id: string | null; trip_id: string | null; office_id: string | null; sla_due_at: string };

type ResolutionResult = { id: string; booking_id: string; status: string; resolved_at: string };

function messageFrom(payload: unknown) {
  if (typeof payload === "object" && payload !== null && "error" in payload && typeof payload.error === "object" && payload.error !== null && "message" in payload.error && typeof payload.error.message === "string") return payload.error.message;
  return "تعذر إكمال العملية.";
}

export function IncidentConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [cases, setCases] = useState<SupportCase[]>([]);
  const [tripId, setTripId] = useState("");
  const [bookingId, setBookingId] = useState("");
  const [resolution, setResolution] = useState("alternative_accepted");
  const [version, setVersion] = useState("1");
  const [outcome, setOutcome] = useState("completed");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function headers(mutation = false) {
    return { Authorization: `Bearer ${token.trim()}`, ...(mutation ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() } : {}) };
  }

  async function loadCases() {
    if (!token.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl("/v1/platform/support-cases?priority=P1"), { headers: headers() });
      const payload = await response.json() as SupportCase[] | unknown;
      if (!response.ok || !Array.isArray(payload)) { setMessage(messageFrom(payload)); return; }
      setCases(payload as SupportCase[]); setMessage("تم تحديث حالات P1 المركزية.");
    } catch { setMessage("تعذر الاتصال بمركز الحوادث."); }
    finally { setLoading(false); }
  }

  async function resolveBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token.trim() || !tripId.trim() || !bookingId.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(`/v1/platform/trips/${encodeURIComponent(tripId.trim())}/interruption/bookings`), {
        method: "POST", headers: headers(true), body: JSON.stringify({ booking_id: bookingId.trim(), resolution, details: { source: "platform_console" } }),
      });
      const payload = await response.json() as ResolutionResult | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("status" in payload)) { setMessage(messageFrom(payload)); return; }
      setMessage(`تم تثبيت حق الحجز: ${(payload as ResolutionResult).status}`);
    } catch { setMessage("تعذر تثبيت معالجة الحجز."); }
    finally { setLoading(false); }
  }

  async function closeIncident() {
    if (!token.trim() || !tripId.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(`/v1/platform/trips/${encodeURIComponent(tripId.trim())}/interruption/close`), {
        method: "POST", headers: headers(true), body: JSON.stringify({ outcome, version: Number(version) }),
      });
      const payload = await response.json() as unknown;
      if (!response.ok) { setMessage(messageFrom(payload)); return; }
      setMessage("أُغلقت الرحلة بعد التأكد من معالجة حقوق جميع الحجوزات.");
    } catch { setMessage("تعذر إغلاق الحادث التشغيلي."); }
    finally { setLoading(false); }
  }

  return (
    <section className="workspace-grid incident-workspace">
      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">مركز الحوادث</p><h2>حالات P1 والتصعيد</h2></div><span className="state-badge state-cancelled">SLA</span></div>
        <div className="stack-form action-row">
          <label>جلسة المنصة<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label>
          <button type="button" className="secondary-button" onClick={loadCases} disabled={loading}>تحديث الحالات</button>
        </div>
        <div className="data-table incident-case-list">
          {cases.map((item) => (
            <button type="button" className="data-row support-case-row" key={item.id} onClick={() => { if (item.trip_id) setTripId(item.trip_id); if (item.booking_id) setBookingId(item.booking_id); }}>
              <div><strong>{item.category}</strong><small>{item.office_id ?? "منصة"} · {item.booking_id ?? "—"}</small></div>
              <span className="state-badge state-cancelled">{item.priority}</span><small>{item.status}</small>
            </button>
          ))}
          {cases.length === 0 ? <div className="empty-state"><p>لا توجد حالات P1 محمّلة.</p></div> : null}
        </div>
      </article>

      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">رحلة متوقفة</p><h2>حقوق كل حجز قبل الإغلاق</h2></div><span className="state-badge state-pending">منع الإغلاق المبكر</span></div>
        <form className="stack-form" onSubmit={resolveBooking}>
          <label>رقم الرحلة<input value={tripId} onChange={(event) => setTripId(event.target.value)} /></label>
          <label>رقم الحجز العام<input value={bookingId} onChange={(event) => setBookingId(event.target.value)} /></label>
          <label>المعالجة<select value={resolution} onChange={(event) => setResolution(event.target.value)}><option value="service_completed">اكتملت الخدمة</option><option value="alternative_accepted">قُبل البديل</option><option value="refund_started">بدأ الاسترداد</option><option value="compensated">تم التعويض</option></select></label>
          <button disabled={loading}>تثبيت معالجة الحجز</button>
        </form>
        <div className="incident-close-box">
          <label>نسخة الرحلة<input type="number" min="1" value={version} onChange={(event) => setVersion(event.target.value)} /></label>
          <label>النتيجة<select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option value="completed">مكتملة</option><option value="cancelled">ملغاة</option></select></label>
          <button type="button" onClick={closeIncident} disabled={loading}>إغلاق الحادث</button>
        </div>
        {message ? <p className="form-note">{message}</p> : null}
      </article>
    </section>
  );
}
