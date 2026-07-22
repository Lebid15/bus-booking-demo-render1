"use client";

import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type Plan = {
  id: string;
  code: string;
  name: string;
  billing_period: string;
  price: { amount: string; currency: string };
  features: Record<string, unknown>;
  limits: Record<string, unknown>;
  status: string;
  version: number;
};

type Invoice = {
  id: string;
  status: string;
  currency: string;
  total_amount: string;
  due_at: string;
  paid_at: string | null;
  payment_reference: string | null;
};

type Subscription = {
  id: string;
  office_id: string;
  plan: Plan;
  status: string;
  period_start: string;
  period_end: string;
  access_mode: string;
  auto_renew: boolean;
  cancel_at_period_end: boolean;
  usage: Record<string, { used: number; limit: number | null; remaining: number | null }>;
  invoices: Invoice[];
};

type ChangeRequest = {
  request_id: string;
  office_id: string;
  office_name: string;
  plan_id: string;
  plan_name: string;
  effective_mode: string;
  status: string;
  requested_at: string;
};

function errorMessage(payload: unknown): string {
  if (
    typeof payload === "object" && payload !== null && "error" in payload &&
    typeof payload.error === "object" && payload.error !== null && "message" in payload.error &&
    typeof payload.error.message === "string"
  ) return payload.error.message;
  return "تعذر إكمال عملية الاشتراك.";
}

function authHeaders(token: string, mutation = false): HeadersInit {
  return {
    Authorization: `Bearer ${token.trim()}`,
    ...(mutation ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() } : {}),
  };
}

export function OfficeSubscriptionConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [planId, setPlanId] = useState("");
  const [effectiveMode, setEffectiveMode] = useState("next_period");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!token.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const [subscriptionResponse, plansResponse] = await Promise.all([
        fetch(browserApiUrl("/v1/office/subscription"), { headers: authHeaders(token) }),
        fetch(browserApiUrl("/v1/office/subscription-plans"), { headers: authHeaders(token) }),
      ]);
      const subscriptionPayload = await subscriptionResponse.json() as Subscription | unknown;
      const plansPayload = await plansResponse.json() as Plan[] | unknown;
      if (subscriptionResponse.ok && typeof subscriptionPayload === "object" && subscriptionPayload !== null && "id" in subscriptionPayload) {
        setSubscription(subscriptionPayload as Subscription);
      } else if (subscriptionResponse.status !== 404) {
        setMessage(errorMessage(subscriptionPayload));
      }
      if (!plansResponse.ok || !Array.isArray(plansPayload)) {
        setMessage(errorMessage(plansPayload)); return;
      }
      setPlans(plansPayload as Plan[]);
      setMessage("تم تحديث الخطة والاستخدام والفواتير.");
    } catch { setMessage("تعذر الاتصال بخدمة الاشتراكات."); }
    finally { setLoading(false); }
  }

  async function requestChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token.trim() || !planId) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl("/v1/office/subscription/change-request"), {
        method: "POST",
        headers: authHeaders(token, true),
        body: JSON.stringify({ plan_id: planId, effective_mode: effectiveMode }),
      });
      const payload = await response.json() as unknown;
      if (!response.ok) { setMessage(errorMessage(payload)); return; }
      setMessage("تم تسجيل طلب تغيير الباقة مع تاريخ النفاذ المحدد.");
    } catch { setMessage("تعذر إرسال طلب تغيير الباقة."); }
    finally { setLoading(false); }
  }

  return (
    <section className="workspace-grid">
      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">الخطة الحالية</p><h2>الاستخدام والفواتير</h2></div><span className="state-badge state-confirmed">Snapshot</span></div>
        <div className="stack-form action-row"><label>جلسة المكتب<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label><button type="button" onClick={load} disabled={loading}>تحميل الاشتراك</button></div>
        {subscription ? (
          <>
            <div className="data-row"><div><strong>{subscription.plan.name}</strong><small>{subscription.period_start.slice(0, 10)} — {subscription.period_end.slice(0, 10)}</small></div><span className="state-badge state-pending">{subscription.status}</span><small>{subscription.plan.price.amount} {subscription.plan.price.currency}</small></div>
            <div className="module-grid compact-grid">
              {Object.entries(subscription.usage).map(([key, value]) => <div className="metric-card" key={key}><span>{key}</span><strong>{value.used}</strong><p>الحد: {value.limit ?? "غير محدود"} · المتبقي: {value.remaining ?? "—"}</p></div>)}
            </div>
            <div className="data-table">
              {subscription.invoices.map((invoice) => <div className="data-row" key={invoice.id}><div><strong>{invoice.total_amount} {invoice.currency}</strong><small>استحقاق {invoice.due_at.slice(0, 10)}</small></div><span className="state-badge state-pending">{invoice.status}</span><small>{invoice.payment_reference ?? "غير مدفوع"}</small></div>)}
            </div>
          </>
        ) : <div className="empty-state"><p>لا يوجد اشتراك محمّل بعد.</p></div>}
        {message ? <p className="form-note">{message}</p> : null}
      </article>

      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">طلب تغيير</p><h2>اختيار الباقة وتاريخ النفاذ</h2></div><span className="state-badge state-pending">مراجعة منصة</span></div>
        <form className="stack-form" onSubmit={requestChange}>
          <label>الباقة<select value={planId} onChange={(event) => setPlanId(event.target.value)}><option value="">اختر باقة</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name} · {plan.price.amount} {plan.price.currency}</option>)}</select></label>
          <label>النفاذ<select value={effectiveMode} onChange={(event) => setEffectiveMode(event.target.value)}><option value="next_period">بداية الفترة القادمة</option><option value="immediate">فوري بعد المراجعة والدفع</option></select></label>
          <button disabled={loading || !planId}>إرسال طلب التغيير</button>
        </form>
      </article>
    </section>
  );
}

export function PlatformSubscriptionConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [changes, setChanges] = useState<ChangeRequest[]>([]);
  const [officeId, setOfficeId] = useState("");
  const [selectedPlan, setSelectedPlan] = useState("");
  const [paymentReference, setPaymentReference] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newPrice, setNewPrice] = useState("0.00");
  const [currency, setCurrency] = useState("SYP");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!token.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const [plansResponse, invoicesResponse, changesResponse] = await Promise.all([
        fetch(browserApiUrl("/v1/platform/subscription-plans"), { headers: authHeaders(token) }),
        fetch(browserApiUrl("/v1/platform/subscription-invoices"), { headers: authHeaders(token) }),
        fetch(browserApiUrl("/v1/platform/subscription-change-requests"), { headers: authHeaders(token) }),
      ]);
      const planPayload = await plansResponse.json() as Plan[] | unknown;
      const invoicePayload = await invoicesResponse.json() as Invoice[] | unknown;
      const changePayload = await changesResponse.json() as ChangeRequest[] | unknown;
      if (!plansResponse.ok || !Array.isArray(planPayload)) { setMessage(errorMessage(planPayload)); return; }
      if (!invoicesResponse.ok || !Array.isArray(invoicePayload)) { setMessage(errorMessage(invoicePayload)); return; }
      if (!changesResponse.ok || !Array.isArray(changePayload)) { setMessage(errorMessage(changePayload)); return; }
      setPlans(planPayload as Plan[]); setInvoices(invoicePayload as Invoice[]); setChanges(changePayload as ChangeRequest[]);
      setMessage("تم تحديث الباقات والفواتير وطلبات التغيير.");
    } catch { setMessage("تعذر تحميل مركز الاشتراكات."); }
    finally { setLoading(false); }
  }

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token.trim() || !newCode.trim() || !newName.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl("/v1/platform/subscription-plans"), {
        method: "POST", headers: authHeaders(token, true),
        body: JSON.stringify({ code: newCode.trim(), name: newName.trim(), billing_period: "monthly", price_amount: newPrice, currency, features: { public_booking: true, reports: true }, limits: { max_branches: 5, max_staff: 20, max_vehicles: 20, max_monthly_trips: 300 }, status: "active" }),
      });
      const payload = await response.json() as Plan | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) { setMessage(errorMessage(payload)); return; }
      setPlans((current) => [payload as Plan, ...current]); setSelectedPlan((payload as Plan).id); setMessage("تم إنشاء الباقة بإصدارها الحالي.");
    } catch { setMessage("تعذر إنشاء الباقة."); }
    finally { setLoading(false); }
  }

  async function assignSubscription() {
    if (!token.trim() || !officeId.trim() || !selectedPlan) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(`/v1/platform/offices/${encodeURIComponent(officeId.trim())}/subscription`), {
        method: "POST", headers: authHeaders(token, true),
        body: JSON.stringify({ plan_id: selectedPlan, status: "active", auto_renew: true, payment_reference: paymentReference.trim() || null }),
      });
      const payload = await response.json() as unknown;
      if (!response.ok) { setMessage(errorMessage(payload)); return; }
      setMessage("تم تعيين الاشتراك مع تثبيت السعر والفترة والحدود."); await load();
    } catch { setMessage("تعذر تعيين الاشتراك."); }
    finally { setLoading(false); }
  }

  async function invoiceCommand(invoiceId: string, command: string) {
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(`/v1/platform/subscription-invoices/${encodeURIComponent(invoiceId)}/commands`), {
        method: "POST", headers: authHeaders(token, true),
        body: JSON.stringify({ command, payment_reference: command === "mark_paid" ? paymentReference.trim() : undefined, reason: "معالجة مالية موثقة" }),
      });
      const payload = await response.json() as unknown;
      if (!response.ok) { setMessage(errorMessage(payload)); return; }
      setMessage(`تم تنفيذ أمر الفاتورة: ${command}`); await load();
    } catch { setMessage("تعذر تنفيذ أمر الفاتورة."); }
    finally { setLoading(false); }
  }

  async function reviewChange(requestId: string, command: string) {
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(`/v1/platform/subscription-change-requests/${encodeURIComponent(requestId)}/commands`), {
        method: "POST", headers: authHeaders(token, true),
        body: JSON.stringify({ command, payment_reference: paymentReference.trim() || null, reason: "مراجعة طلب تغيير الباقة" }),
      });
      const payload = await response.json() as unknown;
      if (!response.ok) { setMessage(errorMessage(payload)); return; }
      setMessage(`تم ${command === "approve" ? "اعتماد" : "رفض"} طلب التغيير.`); await load();
    } catch { setMessage("تعذر مراجعة طلب التغيير."); }
    finally { setLoading(false); }
  }

  return (
    <section className="workspace-grid">
      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">الباقات</p><h2>إنشاء وإسناد خطة</h2></div><span className="state-badge state-confirmed">غير رجعي</span></div>
        <form className="stack-form" onSubmit={createPlan}>
          <label>جلسة المنصة<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label>
          <div className="action-row"><label>رمز الباقة<input value={newCode} onChange={(event) => setNewCode(event.target.value)} /></label><label>الاسم<input value={newName} onChange={(event) => setNewName(event.target.value)} /></label></div>
          <div className="action-row"><label>السعر<input value={newPrice} onChange={(event) => setNewPrice(event.target.value)} /></label><label>العملة<input maxLength={3} value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} /></label></div>
          <div className="action-row"><button disabled={loading}>إنشاء باقة</button><button type="button" className="secondary-button" onClick={load} disabled={loading}>تحديث المركز</button></div>
        </form>
        <hr />
        <div className="stack-form">
          <label>رقم المكتب<input value={officeId} onChange={(event) => setOfficeId(event.target.value)} /></label>
          <label>الخطة<select value={selectedPlan} onChange={(event) => setSelectedPlan(event.target.value)}><option value="">اختر باقة</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name} · {plan.price.amount} {plan.price.currency}</option>)}</select></label>
          <label>مرجع الدفع الاختياري<input value={paymentReference} onChange={(event) => setPaymentReference(event.target.value)} /></label>
          <button type="button" onClick={assignSubscription} disabled={loading || !officeId || !selectedPlan}>تفعيل/تغيير اشتراك المكتب</button>
        </div>
        {message ? <p className="form-note">{message}</p> : null}
      </article>

      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">الفوترة والطلبات</p><h2>التحصيل وتاريخ النفاذ</h2></div><span className="state-badge state-pending">Ledger</span></div>
        <div className="data-table">
          {invoices.map((invoice) => <div className="data-row" key={invoice.id}><div><strong>{invoice.total_amount} {invoice.currency}</strong><small>{invoice.id} · استحقاق {invoice.due_at.slice(0, 10)}</small></div><span className="state-badge state-pending">{invoice.status}</span><div className="action-row"><button type="button" className="secondary-button" onClick={() => invoiceCommand(invoice.id, "mark_paid")} disabled={loading || invoice.status !== "open"}>تثبيت الدفع</button><button type="button" className="secondary-button" onClick={() => invoiceCommand(invoice.id, "void")} disabled={loading || invoice.status !== "open"}>إلغاء</button></div></div>)}
          {changes.map((change) => <div className="data-row" key={change.request_id}><div><strong>{change.office_name} ← {change.plan_name}</strong><small>{change.effective_mode} · {change.requested_at.slice(0, 10)}</small></div><span className="state-badge state-pending">{change.status}</span><div className="action-row"><button type="button" className="secondary-button" onClick={() => reviewChange(change.request_id, "approve")} disabled={loading || change.status !== "pending"}>اعتماد</button><button type="button" className="secondary-button" onClick={() => reviewChange(change.request_id, "reject")} disabled={loading || change.status !== "pending"}>رفض</button></div></div>)}
        </div>
      </article>
    </section>
  );
}
