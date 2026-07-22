"use client";

import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type SupportCase = {
  id: string;
  priority: string;
  category: string;
  status: string;
  booking_id: string | null;
  trip_id: string | null;
  sla_due_at: string;
  metadata: Record<string, unknown>;
};

type RecoveryResult = {
  pnr: string;
  booking_status: string;
  payment_status: string;
  payment_required: boolean;
  passengers: Array<{
    passenger_id: string;
    full_name: string;
    seat_code: string | null;
    boarding_status: string;
    ticket_status: string | null;
  }>;
};

function errorMessage(payload: unknown) {
  if (
    typeof payload === "object" && payload !== null && "error" in payload
    && typeof payload.error === "object" && payload.error !== null
    && "message" in payload.error && typeof payload.error.message === "string"
  ) return payload.error.message;
  return "تعذر إكمال العملية.";
}

export function SupportConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [cases, setCases] = useState<SupportCase[]>([]);
  const [priority, setPriority] = useState("");
  const [caseId, setCaseId] = useState("");
  const [reply, setReply] = useState("");
  const [tripId, setTripId] = useState("");
  const [pnr, setPnr] = useState("");
  const [identityTail, setIdentityTail] = useState("");
  const [recovery, setRecovery] = useState<RecoveryResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function headers(mutation = false) {
    return {
      Authorization: `Bearer ${token.trim()}`,
      ...(mutation ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() } : {}),
    };
  }

  async function loadCases() {
    if (!token.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      const query = new URLSearchParams();
      if (priority) query.set("priority", priority);
      const response = await fetch(browserApiUrl(`/v1/office/support-cases?${query}`), { headers: headers() });
      const payload = await response.json() as SupportCase[] | unknown;
      if (!response.ok || !Array.isArray(payload)) {
        setMessage(errorMessage(payload));
        return;
      }
      setCases(payload as SupportCase[]);
      setMessage("تم تحديث طابور الدعم.");
    } catch {
      setMessage("تعذر الاتصال بخادم الدعم.");
    } finally {
      setLoading(false);
    }
  }

  async function sendReply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!caseId.trim() || !reply.trim() || !token.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(browserApiUrl(`/v1/office/support-cases/${encodeURIComponent(caseId.trim())}/messages`), {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({ body: reply.trim(), visibility: "shared", file_ids: [] }),
      });
      const payload = await response.json() as unknown;
      if (!response.ok) {
        setMessage(errorMessage(payload));
        return;
      }
      setReply("");
      setMessage("تم إرسال الرد وتسجيله في سجل الحالة.");
    } catch {
      setMessage("تعذر إرسال الرد.");
    } finally {
      setLoading(false);
    }
  }

  async function recoveryLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tripId.trim() || !pnr.trim() || !token.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      const query = new URLSearchParams({ pnr: pnr.trim() });
      if (identityTail.trim()) query.set("identity_tail", identityTail.trim());
      const response = await fetch(
        browserApiUrl(`/v1/office/trips/${encodeURIComponent(tripId.trim())}/recovery-lookup?${query}`),
        { headers: headers() },
      );
      const payload = await response.json() as RecoveryResult | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("passengers" in payload)) {
        setRecovery(null);
        setMessage(errorMessage(payload));
        return;
      }
      setRecovery(payload as RecoveryResult);
      setMessage("تم التحقق من القائمة المحلية دون إنشاء دفعة جديدة.");
    } catch {
      setMessage("تعذر تنفيذ التحقق الاحتياطي.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="boarding-workspace support-workspace">
      <article className="workspace-panel">
        <div className="section-heading">
          <div><p className="eyebrow">طابور الدعم</p><h2>الحالات وSLA</h2></div>
          <span className="state-badge state-pending">P1 تلقائي</span>
        </div>
        <div className="stack-form boarding-credentials">
          <label>جلسة الموظف<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label>
          <label>
            الأولوية
            <select value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="">الكل</option><option value="P0">P0</option><option value="P1">P1</option>
              <option value="P2">P2</option><option value="P3">P3</option><option value="P4">P4</option>
            </select>
          </label>
          <button className="secondary-button" type="button" onClick={loadCases} disabled={loading}>تحديث</button>
        </div>
        <div className="data-table">
          {cases.map((item) => (
            <button className="data-row support-case-row" type="button" key={item.id} onClick={() => setCaseId(item.id)}>
              <div><strong>{item.category}</strong><small>{item.booking_id ?? item.trip_id ?? "حالة عامة"}</small></div>
              <span className={`state-badge ${item.priority === "P1" || item.priority === "P0" ? "state-cancelled" : "state-pending"}`}>{item.priority}</span>
              <small>{item.status}</small>
            </button>
          ))}
          {cases.length === 0 ? <div className="empty-state"><p>لا توجد حالات محمّلة.</p></div> : null}
        </div>
        <form className="stack-form support-reply" onSubmit={sendReply}>
          <label>رقم الحالة<input value={caseId} onChange={(event) => setCaseId(event.target.value)} /></label>
          <label>الرد<textarea rows={4} value={reply} onChange={(event) => setReply(event.target.value)} /></label>
          <button disabled={loading}>إرسال الرد</button>
        </form>
      </article>

      <article className="workspace-panel">
        <div className="section-heading">
          <div><p className="eyebrow">استمرارية التشغيل</p><h2>تحقق عند تعطل النظام</h2></div>
          <span className="state-badge state-active">لا دفع جديد</span>
        </div>
        <form className="stack-form" onSubmit={recoveryLookup}>
          <label>رقم الرحلة<input value={tripId} onChange={(event) => setTripId(event.target.value)} /></label>
          <label>PNR<input value={pnr} onChange={(event) => setPnr(event.target.value)} /></label>
          <label>آخر محارف الهوية — اختياري<input value={identityTail} onChange={(event) => setIdentityTail(event.target.value)} /></label>
          <button disabled={loading}>التحقق من الراكب</button>
        </form>
        {recovery ? (
          <>
            <div className="status-banner status-success">
              <strong>{recovery.pnr} · {recovery.booking_status}</strong>
              <span>الدفع المطلوب الآن: {recovery.payment_required ? "نعم" : "لا"}</span>
            </div>
            <div className="data-table support-recovery-table">
              {recovery.passengers.map((passenger) => (
                <div className="data-row" key={passenger.passenger_id}>
                  <div><strong>{passenger.full_name}</strong><small>المقعد {passenger.seat_code ?? "—"}</small></div>
                  <span className="state-badge state-active">{passenger.boarding_status}</span>
                  <small>{passenger.ticket_status ?? "بلا تذكرة"}</small>
                </div>
              ))}
            </div>
          </>
        ) : null}
        {message ? <p className="form-note">{message}</p> : null}
      </article>
    </section>
  );
}
