"use client";

import { FormEvent, useMemo, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type EffectiveSetting = {
  value: unknown;
  value_type: string;
  source: string;
  effective_from: string | null;
  snapshot: boolean;
  bounds: { minimum: string | null; maximum: string | null; choices: string[] | null };
};

type ConfigurationChange = {
  id: string;
  key: string;
  value_json: unknown;
  effective_from: string;
  created_by: string;
  approved_by: string | null;
  reason: string;
  status: string;
};

type ConfigurationPayload = {
  effective: Record<string, EffectiveSetting>;
  pending_changes?: ConfigurationChange[];
  changes?: ConfigurationChange[];
};

const officeDefaults: Record<string, string> = {
  "office.payment.deadline_minutes": "120",
  "office.boarding.open_minutes": "60",
  "office.boarding.close_minutes": "10",
  "office.manual_payment.methods": "cash,transfer",
};

const platformDefaults: Record<string, string> = {
  "platform.booking.default_hold_minutes": "10",
  "platform.booking.max_unpaid_per_phone": "3",
  "platform.gender_adjacency.enabled": "true",
  "platform.refund.dual_approval_threshold": "500000.00",
  "platform.offline_manifest.ttl_hours": "12",
  "platform.risk.manual_review_threshold": "50",
};

function parseValue(raw: string): unknown {
  const trimmed = raw.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (trimmed.includes(",")) return trimmed.split(",").map((item) => item.trim()).filter(Boolean);
  if (/^-?\d+$/.test(trimmed)) return Number.parseInt(trimmed, 10);
  if (/^-?\d+\.\d+$/.test(trimmed)) return trimmed;
  return trimmed;
}

function errorMessage(payload: unknown): string {
  if (
    typeof payload === "object" && payload !== null && "error" in payload &&
    typeof payload.error === "object" && payload.error !== null && "message" in payload.error &&
    typeof payload.error.message === "string"
  ) return payload.error.message;
  return "تعذر تنفيذ تغيير الإعدادات.";
}

export function ConfigurationConsole({ scope }: { scope: "office" | "platform" }) {
  const defaults = useMemo(() => scope === "office" ? officeDefaults : platformDefaults, [scope]);
  const [token, setToken] = useStoredAccessToken();
  const [selectedKey, setSelectedKey] = useState(Object.keys(defaults)[0]);
  const [value, setValue] = useState(defaults[Object.keys(defaults)[0]]);
  const [reason, setReason] = useState("");
  const [effective, setEffective] = useState<Record<string, EffectiveSetting>>({});
  const [pending, setPending] = useState<ConfigurationChange[]>([]);
  const [selectedChangeIds, setSelectedChangeIds] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const endpoint = `/v1/${scope}/configuration`;

  function headers(mutation = false): HeadersInit {
    return {
      Authorization: `Bearer ${token.trim()}`,
      ...(mutation ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() } : {}),
    };
  }

  async function load() {
    if (!token.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(endpoint), { headers: headers() });
      const payload = await response.json() as ConfigurationPayload | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("effective" in payload)) {
        setMessage(errorMessage(payload)); return;
      }
      const data = payload as ConfigurationPayload;
      setEffective(data.effective);
      setPending(data.pending_changes ?? []);
      setMessage("تم تحديث الإعدادات الفعالة والتغييرات المعلقة.");
    } catch { setMessage("تعذر الاتصال بخدمة الإعدادات."); }
    finally { setLoading(false); }
  }

  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token.trim() || !reason.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(endpoint), {
        method: "PATCH",
        headers: headers(true),
        body: JSON.stringify({
          action: "propose",
          changes: { [selectedKey]: parseValue(value) },
          reason: reason.trim(),
          effective_from: new Date().toISOString(),
        }),
      });
      const payload = await response.json() as ConfigurationPayload | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null) { setMessage(errorMessage(payload)); return; }
      const data = payload as ConfigurationPayload;
      setEffective(data.effective ?? effective);
      if (scope === "platform") setPending((current) => [...(data.changes ?? []), ...current]);
      setMessage(scope === "platform" ? "تم إنشاء التغيير وبانتظار اعتماد مستخدم ثانٍ." : "تم اعتماد إعداد المكتب وتسجيل أثره.");
    } catch { setMessage("تعذر حفظ التغيير."); }
    finally { setLoading(false); }
  }

  async function approve() {
    if (scope !== "platform" || selectedChangeIds.length === 0 || !token.trim() || !reason.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const response = await fetch(browserApiUrl(endpoint), {
        method: "PATCH",
        headers: headers(true),
        body: JSON.stringify({ action: "approve", change_ids: selectedChangeIds, reason: reason.trim() }),
      });
      const payload = await response.json() as ConfigurationPayload | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null) { setMessage(errorMessage(payload)); return; }
      setPending((current) => current.filter((item) => !selectedChangeIds.includes(item.id)));
      setSelectedChangeIds([]);
      setMessage("تم اعتماد التغييرات بواسطة المستخدم الثاني.");
      await load();
    } catch { setMessage("تعذر اعتماد التغيير."); }
    finally { setLoading(false); }
  }

  return (
    <section className="workspace-grid">
      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">Configuration registry</p><h2>تعديل محكوم ضمن الحدود</h2></div><span className="state-badge state-confirmed">MFA + Audit</span></div>
        <form className="stack-form" onSubmit={propose}>
          <label>جلسة {scope === "office" ? "المكتب" : "المنصة"}<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label>
          <label>الإعداد<select value={selectedKey} onChange={(event) => { const key = event.target.value; setSelectedKey(key); setValue(defaults[key]); }}>{Object.keys(defaults).map((key) => <option key={key} value={key}>{key}</option>)}</select></label>
          <label>القيمة<input value={value} onChange={(event) => setValue(event.target.value)} /></label>
          <label>سبب التغيير<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          <div className="action-row"><button disabled={loading}>حفظ التغيير</button><button className="secondary-button" type="button" onClick={load} disabled={loading}>تحديث</button></div>
        </form>
        {message ? <p className="form-note">{message}</p> : null}
      </article>

      <article className="workspace-panel">
        <div className="section-heading"><div><p className="eyebrow">Effective values</p><h2>الإعدادات النافذة</h2></div><span className="state-badge state-pending">Versioned</span></div>
        <div className="data-table">
          {Object.entries(effective).map(([key, item]) => <div className="data-row" key={key}><div><strong>{key}</strong><small>{JSON.stringify(item.value)} · {item.source}</small></div><span className="state-badge state-confirmed">{item.value_type}</span><small>{item.bounds.minimum ?? "—"} → {item.bounds.maximum ?? item.bounds.choices?.join("، ") ?? "—"}</small></div>)}
          {Object.keys(effective).length === 0 ? <div className="empty-state"><p>حمّل الإعدادات لعرض القيم الفعالة.</p></div> : null}
        </div>
      </article>

      {scope === "platform" ? <article className="workspace-panel table-panel">
        <div className="section-heading"><div><p className="eyebrow">Dual approval</p><h2>تغييرات بانتظار الاعتماد</h2></div><button type="button" onClick={approve} disabled={loading || selectedChangeIds.length === 0}>اعتماد المحدد</button></div>
        <div className="data-table">
          {pending.map((item) => <label className="data-row" key={item.id}><input type="checkbox" checked={selectedChangeIds.includes(item.id)} onChange={(event) => setSelectedChangeIds((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /><div><strong>{item.key}</strong><small>{JSON.stringify(item.value_json)} · {item.reason}</small></div><span className="state-badge state-pending">{item.status}</span></label>)}
          {pending.length === 0 ? <div className="empty-state"><p>لا توجد تغييرات معلقة.</p></div> : null}
        </div>
      </article> : null}
    </section>
  );
}
