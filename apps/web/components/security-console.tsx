"use client";

import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type DataSubjectResponse = { request_id: string; status?: string };
type RiskAssessment = {
  id: string;
  subject_type: string;
  subject_id: string;
  score: string;
  decision: string;
  model_version: string;
  signals: Record<string, unknown>;
  review_status: string | null;
  created_at: string;
};
type LegalHold = {
  id: string;
  subject_type: string;
  subject_id: string;
  reason: string;
  active: boolean;
  placed_at: string;
  released_at: string | null;
};

type ErrorEnvelope = { error?: { message?: string } };

const holdSubjectTypes = ["booking", "user", "payment", "dispute", "office"];
const riskDecisions = ["allow", "step_up", "manual_review", "restrict", "block"];
const riskSubjectTypes = ["booking", "payment", "user", "office", "employee", "device"];

function errorMessage(payload: unknown): string {
  if (typeof payload === "object" && payload !== null) {
    const envelope = payload as ErrorEnvelope;
    if (typeof envelope.error?.message === "string") return envelope.error.message;
  }
  return "تعذر إكمال العملية.";
}

function authHeaders(token: string, mutation = false): HeadersInit {
  return {
    Authorization: `Bearer ${token.trim()}`,
    ...(mutation
      ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }
      : {}),
  };
}

export function UserPrivacyConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [request, setRequest] = useState<DataSubjectResponse | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(path: string, body?: Record<string, string>) {
    if (!token.trim()) {
      setMessage("أدخل جلسة المستخدم أولًا.");
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(browserApiUrl(path), {
        method: "POST",
        headers: authHeaders(token, true),
        body: body ? JSON.stringify(body) : undefined,
      });
      const payload = (await response.json()) as DataSubjectResponse | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("request_id" in payload)) {
        setMessage(errorMessage(payload));
        return;
      }
      setRequest(payload as DataSubjectResponse);
      setMessage(path.endsWith("delete-account")
        ? "تم تنفيذ طلب تعطيل وإخفاء الحساب مع الاحتفاظ بالسجلات الملزمة."
        : "تم تسجيل طلب تصدير البيانات.");
      if (path.endsWith("delete-account")) setConfirmation("");
    } catch {
      setMessage("تعذر الاتصال بخدمة الخصوصية.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace-grid privacy-workspace">
      <article className="workspace-panel">
        <div className="section-heading">
          <div><p className="eyebrow">Data rights</p><h2>حقوق بياناتي</h2></div>
        </div>
        <label className="stack-form">
          جلسة المستخدم
          <input type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" />
        </label>
        <div className="privacy-actions">
          <div className="security-card">
            <div><strong>تصدير البيانات</strong><p>إنشاء طلب رسمي لتجهيز نسخة من البيانات الشخصية المرتبطة بالحساب.</p></div>
            <button onClick={() => submit("/v1/me/data-export")} disabled={loading}>طلب التصدير</button>
          </div>
          <div className="security-card danger-card">
            <div><strong>تعطيل وإخفاء الحساب</strong><p>تُخفى البيانات غير الضرورية، مع بقاء الحجوزات والسجلات المالية التي يفرض النظام الاحتفاظ بها.</p></div>
            <label>اكتب DELETE للتأكيد<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
            <button className="danger-button" onClick={() => submit("/v1/me/delete-account", { confirmation })} disabled={loading || confirmation !== "DELETE"}>تعطيل الحساب</button>
          </div>
        </div>
        {request ? <div className="result-card"><strong>رقم الطلب</strong><code>{request.request_id}</code><span className="state-badge state-pending">{request.status ?? "submitted"}</span></div> : null}
        {message ? <p className="form-note">{message}</p> : null}
      </article>
      <article className="workspace-panel compact-panel">
        <p className="eyebrow">Privacy controls</p>
        <h2>كيف تُحمى البيانات؟</h2>
        <ul className="security-points">
          <li>لا تُحذف القيود المالية أو الحجوزات التي يجب الاحتفاظ بها قانونيًا.</li>
          <li>يوقف Legal Hold عمليات الإتلاف المقررة ويُسجّل سبب التجاوز.</li>
          <li>تُخفى الهوية وبيانات الاتصال غير الضرورية عند إغلاق الحساب.</li>
          <li>لا تُخزن أسرار الدفع أو رموز الجلسات داخل سجل التدقيق.</li>
        </ul>
      </article>
    </section>
  );
}

export function PlatformSecurityConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [risks, setRisks] = useState<RiskAssessment[]>([]);
  const [holds, setHolds] = useState<LegalHold[]>([]);
  const [decision, setDecision] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("");
  const [holdSubjectType, setHoldSubjectType] = useState("user");
  const [holdSubjectId, setHoldSubjectId] = useState("");
  const [holdReason, setHoldReason] = useState("");
  const [releaseReason, setReleaseReason] = useState("انتهاء سبب الاحتفاظ القانوني");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!token.trim()) {
      setMessage("أدخل جلسة إدارة المنصة أولًا.");
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const query = new URLSearchParams();
      if (decision) query.set("decision", decision);
      if (subjectFilter) query.set("subject_type", subjectFilter);
      const [riskResponse, holdResponse] = await Promise.all([
        fetch(browserApiUrl(`/v1/platform/risk-assessments?${query.toString()}`), { headers: authHeaders(token) }),
        fetch(browserApiUrl("/v1/platform/legal-holds"), { headers: authHeaders(token) }),
      ]);
      const riskPayload = (await riskResponse.json()) as RiskAssessment[] | unknown;
      const holdPayload = (await holdResponse.json()) as LegalHold[] | unknown;
      if (!riskResponse.ok || !Array.isArray(riskPayload)) {
        setMessage(errorMessage(riskPayload));
        return;
      }
      if (!holdResponse.ok || !Array.isArray(holdPayload)) {
        setMessage(errorMessage(holdPayload));
        return;
      }
      setRisks(riskPayload);
      setHolds(holdPayload);
      setMessage("تم تحديث مركز الأمان والخصوصية.");
    } catch {
      setMessage("تعذر الاتصال بخدمات الأمان.");
    } finally {
      setLoading(false);
    }
  }

  async function placeHold(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const response = await fetch(browserApiUrl("/v1/platform/legal-holds"), {
      method: "POST",
      headers: authHeaders(token, true),
      body: JSON.stringify({ subject_type: holdSubjectType, subject_id: holdSubjectId, reason: holdReason }),
    });
    const payload = (await response.json()) as LegalHold | unknown;
    if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) {
      setMessage(errorMessage(payload));
      return;
    }
    setHolds((current) => [payload as LegalHold, ...current]);
    setHoldSubjectId("");
    setHoldReason("");
    setMessage("تم وضع Legal Hold وتسجيله في سجل التدقيق.");
  }

  async function releaseHold(id: string) {
    const response = await fetch(browserApiUrl(`/v1/platform/legal-holds/${encodeURIComponent(id)}/release`), {
      method: "POST",
      headers: authHeaders(token, true),
      body: JSON.stringify({ reason: releaseReason }),
    });
    const payload = (await response.json()) as LegalHold | unknown;
    if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) {
      setMessage(errorMessage(payload));
      return;
    }
    setHolds((current) => current.map((item) => item.id === id ? payload as LegalHold : item));
    setMessage("تم تحرير Legal Hold مع الاحتفاظ بسجل وضعه وتحريره.");
  }

  return (
    <section className="security-console">
      <article className="workspace-panel">
        <div className="section-heading">
          <div><p className="eyebrow">Security operations</p><h2>مركز الأمان والخصوصية</h2></div>
          <button onClick={load} disabled={loading}>تحديث</button>
        </div>
        <div className="stack-form security-filters">
          <label>جلسة إدارة المنصة<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label>
          <label>قرار المخاطر<select value={decision} onChange={(event) => setDecision(event.target.value)}><option value="">الكل</option>{riskDecisions.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>نوع الكيان<select value={subjectFilter} onChange={(event) => setSubjectFilter(event.target.value)}><option value="">الكل</option>{riskSubjectTypes.map((value) => <option key={value}>{value}</option>)}</select></label>
        </div>
        <div className="security-metrics">
          <div><strong>{risks.length}</strong><span>تقييمات محمّلة</span></div>
          <div><strong>{risks.filter((item) => item.decision === "step_up").length}</strong><span>Step-up</span></div>
          <div><strong>{risks.filter((item) => ["manual_review", "restrict", "block"].includes(item.decision)).length}</strong><span>تحتاج متابعة</span></div>
          <div><strong>{holds.filter((item) => item.active).length}</strong><span>Legal Hold نشط</span></div>
        </div>
        {message ? <p className="form-note">{message}</p> : null}
      </article>

      <section className="workspace-grid">
        <article className="workspace-panel">
          <div className="section-heading"><div><p className="eyebrow">Risk assessments</p><h2>تقييمات المخاطر</h2></div></div>
          <div className="data-table">
            {risks.map((item) => <div className="data-row risk-row" key={item.id}>
              <div><strong>{item.subject_type} · {item.subject_id}</strong><small>{item.model_version} · {new Date(item.created_at).toLocaleString("ar")}</small><small>{Object.keys(item.signals).join("، ") || "لا توجد إشارات مسجلة"}</small></div>
              <strong className="risk-score">{item.score}</strong>
              <span className={`state-badge ${item.decision === "allow" ? "state-active" : item.decision === "step_up" ? "state-pending" : "state-cancelled"}`}>{item.decision}</span>
            </div>)}
            {risks.length === 0 ? <div className="empty-state"><p>لا توجد تقييمات محمّلة.</p></div> : null}
          </div>
        </article>

        <article className="workspace-panel compact-panel">
          <div className="section-heading"><div><p className="eyebrow">Legal hold</p><h2>الاحتفاظ القانوني</h2></div></div>
          <form className="stack-form" onSubmit={placeHold}>
            <label>نوع الكيان<select value={holdSubjectType} onChange={(event) => setHoldSubjectType(event.target.value)}>{holdSubjectTypes.map((value) => <option key={value}>{value}</option>)}</select></label>
            <label>معرف الكيان UUID<input required value={holdSubjectId} onChange={(event) => setHoldSubjectId(event.target.value)} /></label>
            <label>سبب الاحتفاظ<textarea required minLength={5} value={holdReason} onChange={(event) => setHoldReason(event.target.value)} rows={3} /></label>
            <button disabled={!token.trim()}>وضع Legal Hold</button>
          </form>
          <label className="stack-form release-reason">سبب التحرير<input value={releaseReason} onChange={(event) => setReleaseReason(event.target.value)} /></label>
          <div className="legal-hold-list">
            {holds.map((item) => <article className="legal-hold-item" key={item.id}>
              <div><strong>{item.subject_type} · {item.subject_id}</strong><p>{item.reason}</p><small>{new Date(item.placed_at).toLocaleString("ar")}</small></div>
              {item.active ? <button className="secondary-button" onClick={() => releaseHold(item.id)} disabled={releaseReason.trim().length < 5}>تحرير</button> : <span className="state-badge state-active">محرر</span>}
            </article>)}
            {holds.length === 0 ? <div className="empty-state"><p>لا توجد أوامر احتفاظ محمّلة.</p></div> : null}
          </div>
        </article>
      </section>
    </section>
  );
}
