"use client";

import { FormEvent, useMemo, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type Notice = {
  id: string; event_type: string; rendered_subject: string; rendered_body: string;
  status: string; action_required: boolean; action_url: string | null; read_at: string | null; created_at: string;
};
type Preference = { event_type: string; channel: string; enabled: boolean; updated_at?: string };
type Delivery = {
  id: string; channel: string; status: string; attempt_no: number; next_attempt_at: string | null;
  error_code: string | null; permanent_failure: boolean;
  notification: Notice;
};

const eventTypes = ["booking.created", "payment.succeeded", "trip.material_change", "ticket.reissued", "refund.succeeded"];
const channels = ["in_app", "email", "sms", "push"];

function errorMessage(payload: unknown): string {
  if (typeof payload === "object" && payload !== null && "error" in payload && typeof payload.error === "object" && payload.error !== null && "message" in payload.error && typeof payload.error.message === "string") return payload.error.message;
  return "تعذر إكمال العملية.";
}

function authHeaders(token: string, mutation = false): HeadersInit {
  return { Authorization: `Bearer ${token.trim()}`, ...(mutation ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() } : {}) };
}

export function UserNotificationConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [notices, setNotices] = useState<Notice[]>([]);
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [pushToken, setPushToken] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const matrix = useMemo(() => new Map(preferences.map((item) => [`${item.event_type}:${item.channel}`, item.enabled])), [preferences]);

  async function load() {
    if (!token.trim()) return;
    setLoading(true); setMessage(null);
    try {
      const [noticeResponse, preferenceResponse] = await Promise.all([
        fetch(browserApiUrl("/v1/me/notifications"), { headers: authHeaders(token) }),
        fetch(browserApiUrl("/v1/me/notifications/preferences"), { headers: authHeaders(token) }),
      ]);
      const noticePayload = await noticeResponse.json() as Notice[] | unknown;
      const preferencePayload = await preferenceResponse.json() as Preference[] | unknown;
      if (!noticeResponse.ok || !Array.isArray(noticePayload)) { setMessage(errorMessage(noticePayload)); return; }
      if (!preferenceResponse.ok || !Array.isArray(preferencePayload)) { setMessage(errorMessage(preferencePayload)); return; }
      setNotices(noticePayload); setPreferences(preferencePayload); setMessage("تم تحديث مركز الإشعارات.");
    } catch { setMessage("تعذر الاتصال بخدمة الإشعارات."); }
    finally { setLoading(false); }
  }

  async function markRead(id: string) {
    const response = await fetch(browserApiUrl(`/v1/me/notifications/${encodeURIComponent(id)}/read`), { method: "POST", headers: authHeaders(token, true) });
    const payload = await response.json() as Notice | unknown;
    if (!response.ok || typeof payload !== "object" || payload === null) { setMessage(errorMessage(payload)); return; }
    setNotices((current) => current.map((item) => item.id === id ? payload as Notice : item));
  }

  function toggle(eventType: string, channel: string) {
    const key = `${eventType}:${channel}`;
    const enabled = !(matrix.get(key) ?? true);
    setPreferences((current) => [...current.filter((item) => !(item.event_type === eventType && item.channel === channel)), { event_type: eventType, channel, enabled }]);
  }

  async function savePreferences() {
    const rows = eventTypes.flatMap((eventType) => channels.map((channel) => ({ event_type: eventType, channel, enabled: matrix.get(`${eventType}:${channel}`) ?? true })));
    const response = await fetch(browserApiUrl("/v1/me/notifications/preferences"), { method: "PATCH", headers: authHeaders(token, true), body: JSON.stringify({ preferences: rows }) });
    const payload = await response.json() as Preference[] | unknown;
    if (!response.ok || !Array.isArray(payload)) { setMessage(errorMessage(payload)); return; }
    setPreferences(payload); setMessage("تم حفظ تفضيلات القنوات.");
  }

  async function registerPush(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const response = await fetch(browserApiUrl("/v1/me/push-subscriptions"), { method: "POST", headers: authHeaders(token, true), body: JSON.stringify({ token: pushToken, platform: "web" }) });
    const payload = await response.json() as unknown;
    if (!response.ok) { setMessage(errorMessage(payload)); return; }
    setPushToken(""); setMessage("تم تسجيل اشتراك Push بصورة مشفرة.");
  }

  return <section className="workspace-grid notification-workspace">
    <article className="workspace-panel">
      <div className="section-heading"><div><p className="eyebrow">In-app inbox</p><h2>إشعاراتي</h2></div><button className="secondary-button" onClick={load} disabled={loading}>تحديث</button></div>
      <label className="stack-form">جلسة المستخدم<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label>
      <div className="notification-list">{notices.map((item) => <article className={`notification-item ${item.read_at ? "" : "notification-unread"}`} key={item.id}>
        <div><strong>{item.rendered_subject || item.event_type}</strong><p>{item.rendered_body}</p><small>{new Date(item.created_at).toLocaleString("ar")}</small></div>
        <div className="action-row">{item.action_required && item.action_url ? <a className="primary-link" href={item.action_url}>الإجراء المطلوب</a> : null}{!item.read_at ? <button className="secondary-button" onClick={() => markRead(item.id)}>تمت القراءة</button> : <span className="state-badge state-active">مقروء</span>}</div>
      </article>)}{notices.length === 0 ? <div className="empty-state"><p>لا توجد إشعارات محمّلة.</p></div> : null}</div>
      {message ? <p className="form-note">{message}</p> : null}
    </article>
    <article className="workspace-panel compact-panel">
      <div className="section-heading"><div><p className="eyebrow">Preferences</p><h2>القنوات</h2></div><button onClick={savePreferences} disabled={loading}>حفظ</button></div>
      <div className="preference-grid">{eventTypes.map((eventType) => <div className="preference-row" key={eventType}><strong>{eventType}</strong>{channels.map((channel) => <label key={channel}><input type="checkbox" checked={matrix.get(`${eventType}:${channel}`) ?? true} onChange={() => toggle(eventType, channel)} />{channel}</label>)}</div>)}</div>
      <form className="stack-form push-form" onSubmit={registerPush}><label>رمز Push للجهاز<input minLength={16} value={pushToken} onChange={(event) => setPushToken(event.target.value)} /></label><button>تسجيل الجهاز</button></form>
    </article>
  </section>;
}

export function OfficeNotificationConsole() {
  const [token, setToken] = useStoredAccessToken(); const [items, setItems] = useState<Notice[]>([]); const [message, setMessage] = useState<string | null>(null);
  async function load() { const response = await fetch(browserApiUrl("/v1/office/notifications"), { headers: authHeaders(token) }); const payload = await response.json() as Notice[] | unknown; if (!response.ok || !Array.isArray(payload)) { setMessage(errorMessage(payload)); return; } setItems(payload); setMessage("تم تحديث إشعارات المكتب."); }
  return <section className="workspace-panel"><div className="section-heading"><div><p className="eyebrow">Office inbox</p><h2>الإشعارات التشغيلية</h2></div><button onClick={load}>تحديث</button></div><label className="stack-form">جلسة المكتب<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label><div className="notification-list">{items.map((item) => <article className="notification-item" key={item.id}><div><strong>{item.rendered_subject || item.event_type}</strong><p>{item.rendered_body}</p></div><span className="state-badge state-pending">{item.status}</span></article>)}</div>{message ? <p className="form-note">{message}</p> : null}</section>;
}

export function PlatformNotificationConsole() {
  const [token, setToken] = useStoredAccessToken(); const [status, setStatus] = useState(""); const [channel, setChannel] = useState(""); const [items, setItems] = useState<Delivery[]>([]); const [message, setMessage] = useState<string | null>(null);
  async function load() { const query = new URLSearchParams(); if (status) query.set("status", status); if (channel) query.set("channel", channel); const response = await fetch(browserApiUrl(`/v1/platform/notification-deliveries?${query}`), { headers: authHeaders(token) }); const payload = await response.json() as { results?: Delivery[] } | unknown; if (!response.ok || typeof payload !== "object" || payload === null || !("results" in payload) || !Array.isArray(payload.results)) { setMessage(errorMessage(payload)); return; } setItems(payload.results); setMessage("تم تحديث محاولات التسليم."); }
  async function retry(id: string) { const response = await fetch(browserApiUrl(`/v1/platform/notification-deliveries/${encodeURIComponent(id)}/retry`), { method: "POST", headers: authHeaders(token, true) }); const payload = await response.json() as unknown; if (!response.ok) { setMessage(errorMessage(payload)); return; } setMessage("تم إنشاء محاولة إعادة إرسال جديدة دون تكرار الرسالة المنطقية."); await load(); }
  return <section className="workspace-panel"><div className="section-heading"><div><p className="eyebrow">Delivery operations</p><h2>محاولات التسليم</h2></div><button onClick={load}>تحديث</button></div><div className="stack-form notification-filters"><label>جلسة المنصة<input type="password" value={token} onChange={(event) => setToken(event.target.value)} /></label><label>الحالة<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">الكل</option>{["queued","sending","sent","delivered","failed","bounced"].map((value) => <option key={value}>{value}</option>)}</select></label><label>القناة<select value={channel} onChange={(event) => setChannel(event.target.value)}><option value="">الكل</option>{channels.map((value) => <option key={value}>{value}</option>)}</select></label></div><div className="data-table">{items.map((item) => <div className="data-row notification-delivery-row" key={item.id}><div><strong>{item.notification.rendered_subject || item.notification.event_type}</strong><small>{item.channel} · المحاولة {item.attempt_no} · {item.error_code ?? "دون خطأ"}</small></div><span className={`state-badge ${item.status === "failed" ? "state-cancelled" : "state-active"}`}>{item.status}</span><button className="secondary-button" onClick={() => retry(item.id)}>إعادة</button></div>)}</div>{message ? <p className="form-note">{message}</p> : null}</section>;
}
