"use client";

import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type SettlementItem = {
  id: string;
  type: string;
  booking_id: string | null;
  amount: string;
  currency: string;
  description: string | null;
};

type Settlement = {
  id: string;
  office_id: string;
  period_start: string;
  period_end: string;
  currency: string;
  status: string;
  gross_amount: string;
  commission_amount: string;
  refund_amount: string;
  reserve_amount: string;
  adjustment_amount: string;
  net_amount: string;
  items?: SettlementItem[];
};

function errorMessage(payload: unknown): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "error" in payload &&
    typeof payload.error === "object" &&
    payload.error !== null &&
    "message" in payload.error &&
    typeof payload.error.message === "string"
  ) return payload.error.message;
  return "تعذر إكمال العملية المالية.";
}

function yesterday(): string {
  const value = new Date();
  value.setDate(value.getDate() - 1);
  return value.toISOString().slice(0, 10);
}

export function SettlementConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [officeId, setOfficeId] = useState("");
  const [periodStart, setPeriodStart] = useState(yesterday());
  const [periodEnd, setPeriodEnd] = useState(yesterday());
  const [currency, setCurrency] = useState("SYP");
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [paymentReference, setPaymentReference] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function headers(mutation = false): HeadersInit {
    return {
      Authorization: `Bearer ${token.trim()}`,
      ...(mutation ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() } : {}),
    };
  }

  async function loadSettlements() {
    if (!token.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const query = officeId.trim() ? `?office_id=${encodeURIComponent(officeId.trim())}` : "";
      const response = await fetch(browserApiUrl(`/v1/platform/settlements${query}`), { headers: headers() });
      const payload = await response.json() as Settlement[] | unknown;
      if (!response.ok || !Array.isArray(payload)) { setMessage(errorMessage(payload)); return; }
      setSettlements(payload as Settlement[]);
      setMessage("تم تحديث دورات التسوية.");
    } catch { setMessage("تعذر الاتصال بخدمة التسويات."); }
    finally { setLoading(false); }
  }

  async function createCycle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token.trim() || !officeId.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl("/v1/platform/settlements"), {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({ office_id: officeId.trim(), period_start: periodStart, period_end: periodEnd, currency }),
      });
      const payload = await response.json() as Settlement | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) {
        setMessage(errorMessage(payload)); return;
      }
      const created = payload as Settlement;
      setSelectedId(created.id);
      setSettlements((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setMessage("تم إنشاء دورة التسوية كمسودة.");
    } catch { setMessage("تعذر إنشاء دورة التسوية."); }
    finally { setLoading(false); }
  }

  async function command(commandName: string) {
    if (!token.trim() || !selectedId.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(`/v1/platform/settlements/${encodeURIComponent(selectedId)}/commands`), {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({ command: commandName, payment_reference: paymentReference.trim() || null }),
      });
      const payload = await response.json() as Settlement | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) {
        setMessage(errorMessage(payload)); return;
      }
      const updated = payload as Settlement;
      setSettlements((current) => [updated, ...current.filter((item) => item.id !== updated.id)]);
      setMessage(`تم تنفيذ الأمر: ${commandName}`);
    } catch { setMessage("تعذر تنفيذ أمر التسوية."); }
    finally { setLoading(false); }
  }

  return (
    <section className="workspace-grid">
      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">دورة مالية</p><h2>إنشاء وحساب التسوية</h2></div><span className="state-badge state-pending">عملة واحدة</span></div>
        <form className="stack-form" onSubmit={createCycle}>
          <label>جلسة المنصة<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label>
          <label>رقم المكتب<input value={officeId} onChange={(event) => setOfficeId(event.target.value)} /></label>
          <div className="action-row">
            <label>بداية الفترة<input type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} /></label>
            <label>نهاية الفترة<input type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} /></label>
          </div>
          <label>العملة<input maxLength={3} value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} /></label>
          <div className="action-row"><button disabled={loading}>إنشاء المسودة</button><button type="button" className="secondary-button" onClick={loadSettlements} disabled={loading}>تحديث القائمة</button></div>
        </form>
        {message ? <p className="form-note">{message}</p> : null}
      </article>

      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">فصل الواجبات</p><h2>المراجعة والاعتماد والدفع</h2></div><span className="state-badge state-confirmed">Dual approval</span></div>
        <label>التسوية المختارة<select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}><option value="">اختر دورة</option>{settlements.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.currency} · {item.status}</option>)}</select></label>
        <label>مرجع الدفع<input value={paymentReference} onChange={(event) => setPaymentReference(event.target.value)} placeholder="مطلوب عند تثبيت الدفع" /></label>
        <div className="action-row settlement-actions">
          {[
            ["calculate", "حساب"], ["submit_review", "إرسال للمراجعة"], ["approve", "اعتماد"],
            ["process", "بدء التنفيذ"], ["mark_paid", "تثبيت الدفع"], ["close", "إغلاق"],
          ].map(([value, label]) => <button type="button" key={value} className="secondary-button" onClick={() => command(value)} disabled={loading || !selectedId}>{label}</button>)}
        </div>
        <div className="data-table">
          {settlements.map((item) => (
            <button className="data-row" type="button" key={item.id} onClick={() => setSelectedId(item.id)}>
              <div><strong>{item.currency} · {item.net_amount}</strong><small>{item.period_start} — {item.period_end}</small></div>
              <span className="state-badge state-pending">{item.status}</span>
              <small>مجمد {item.reserve_amount} · عمولة {item.commission_amount}</small>
            </button>
          ))}
          {settlements.length === 0 ? <div className="empty-state"><p>لم تُحمّل دورات تسوية بعد.</p></div> : null}
        </div>
      </article>
    </section>
  );
}

export function OfficeSettlementViewer() {
  const [token, setToken] = useStoredAccessToken();
  const [rows, setRows] = useState<Settlement[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    try {
      const response = await fetch(browserApiUrl("/v1/office/settlements"), { headers: { Authorization: `Bearer ${token.trim()}` } });
      const payload = await response.json() as Settlement[] | unknown;
      if (!response.ok || !Array.isArray(payload)) { setMessage(errorMessage(payload)); return; }
      setRows(payload as Settlement[]); setMessage("تم تحديث كشف التسويات.");
    } catch { setMessage("تعذر تحميل تسويات المكتب."); }
  }

  return (
    <section className="workspace-panel">
      <div className="section-heading"><div><p className="eyebrow">كشف المكتب</p><h2>التسويات حسب العملة والدورة</h2></div><span className="state-badge state-confirmed">قراءة فقط</span></div>
      <div className="stack-form action-row"><label>جلسة المكتب<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label><button type="button" onClick={load}>تحميل</button></div>
      <div className="data-table">
        {rows.map((item) => <div className="data-row" key={item.id}><div><strong>{item.net_amount} {item.currency}</strong><small>{item.period_start} — {item.period_end}</small></div><span className="state-badge state-pending">{item.status}</span><small>مجمد: {item.reserve_amount}</small></div>)}
      </div>
      {message ? <p className="form-note">{message}</p> : null}
    </section>
  );
}
