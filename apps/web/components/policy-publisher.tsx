"use client";

import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type Policy = { id: string; code: string; version_no: number; language: string; title: string; effective_from: string; published_at: string | null; content_sha256: string };

function messageFrom(payload: unknown): string {
  if (typeof payload === "object" && payload !== null && "error" in payload && typeof payload.error === "object" && payload.error !== null && "message" in payload.error && typeof payload.error.message === "string") return payload.error.message;
  return "تعذر تنفيذ عملية السياسة.";
}

export function PolicyPublisher() {
  const [token, setToken] = useStoredAccessToken();
  const [code, setCode] = useState("customer_terms");
  const [policyType, setPolicyType] = useState("terms");
  const [title, setTitle] = useState("شروط استخدام الزبون");
  const [content, setContent] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  function headers(mutation = false): HeadersInit { return { Authorization: `Bearer ${token.trim()}`, ...(mutation ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() } : {}) }; }

  async function load() {
    try {
      if (!effectiveFrom) { setMessage("حدد تاريخ نفاذ الإصدار."); return; }
      const response = await fetch(browserApiUrl("/v1/platform/policies"), { headers: headers() });
      const payload = await response.json() as Policy[] | unknown;
      if (!response.ok || !Array.isArray(payload)) { setMessage(messageFrom(payload)); return; }
      setPolicies(payload as Policy[]); setMessage("تم تحديث إصدارات السياسات.");
    } catch { setMessage("تعذر الاتصال بمركز السياسات."); }
  }

  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const response = await fetch(browserApiUrl("/v1/platform/policies"), {
        method: "POST", headers: headers(true),
        body: JSON.stringify({ template_code: code, policy_type: policyType, owner_scope: "platform", language: "ar", title, content_markdown: content, rules_json: {}, effective_from: new Date(effectiveFrom).toISOString(), publish: true }),
      });
      const payload = await response.json() as Policy | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) { setMessage(messageFrom(payload)); return; }
      setPolicies((current) => [payload as Policy, ...current]); setMessage("تم إنشاء إصدار جديد دون تعديل الحجوزات القائمة.");
    } catch { setMessage("تعذر نشر إصدار السياسة."); }
  }

  return <section className="workspace-grid">
    <article className="workspace-panel"><div className="section-heading"><div><p className="eyebrow">Policy versioning</p><h2>إنشاء إصدار مستقبلي</h2></div><span className="state-badge state-confirmed">SHA-256</span></div><form className="stack-form" onSubmit={publish}><label>جلسة المنصة<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label><label>رمز القالب<input value={code} onChange={(event) => setCode(event.target.value)} /></label><label>نوع السياسة<select value={policyType} onChange={(event) => setPolicyType(event.target.value)}><option value="terms">الشروط</option><option value="privacy">الخصوصية</option><option value="payment">الدفع</option><option value="cancellation">الإلغاء</option><option value="boarding">الصعود</option><option value="baggage">الأمتعة</option></select></label><label>العنوان<input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>تاريخ النفاذ<input required type="datetime-local" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label><label>النص الكامل<textarea value={content} onChange={(event) => setContent(event.target.value)} /></label><div className="action-row"><button>إنشاء الإصدار</button><button type="button" className="secondary-button" onClick={load}>تحديث القائمة</button></div></form>{message ? <p className="form-note">{message}</p> : null}</article>
    <article className="workspace-panel"><div className="section-heading"><div><p className="eyebrow">Immutable history</p><h2>سجل الإصدارات</h2></div><span className="state-badge state-pending">Snapshot safe</span></div><div className="data-table">{policies.map((policy) => <div className="data-row" key={policy.id}><div><strong>{policy.title}</strong><small>{policy.code} · v{policy.version_no} · {policy.language}</small></div><span className="state-badge state-confirmed">{policy.published_at ? "منشور" : "مسودة"}</span><small>{policy.effective_from}<br />{policy.content_sha256?.slice(0, 12)}…</small></div>)}{policies.length === 0 ? <div className="empty-state"><p>حمّل الإصدارات الحالية.</p></div> : null}</div></article>
  </section>;
}
