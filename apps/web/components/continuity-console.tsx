"use client";

import { useState } from "react";
import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type Overview = { state?: { mode: string; reason: string; reconciliation_required: boolean }; latest_reconciliation?: { status: string } | null; open_sev1?: number };

export function ContinuityConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [message, setMessage] = useState("");

  async function call(path: string, options?: RequestInit) {
    setMessage("جارٍ التنفيذ…");
    const response = await fetch(browserApiUrl(path), {
      ...options,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(options?.headers ?? {}) },
    });
    const data = await response.json();
    if (!response.ok) { setMessage(data.error?.message ?? "تعذر التنفيذ"); return null; }
    setMessage("تم التنفيذ بنجاح");
    return data;
  }

  async function refresh() { const data = await call("/v1/platform/continuity"); if (data) setOverview(data); }
  async function command(command: string) {
    await call("/v1/platform/continuity/commands", { method: "POST", body: JSON.stringify({ command, reason: `console:${command}` }) });
    await refresh();
  }

  return <section className="workspace-panel">
    <label>رمز جلسة مدير المنصة<input dir="ltr" value={token} onChange={(e) => setToken(e.target.value)} /></label>
    <div className="action-row">
      <button type="button" onClick={refresh}>تحديث الحالة</button>
      <button type="button" onClick={() => command("maintenance")}>وضع الصيانة</button>
      <button type="button" onClick={() => command("recovery")}>وضع التعافي</button>
      <button type="button" onClick={() => command("reconcile")}>تشغيل المصالحة</button>
      <button type="button" onClick={() => command("reopen")}>إعادة الفتح</button>
    </div>
    <p role="status" aria-live="polite">{message}</p>
    {overview ? <div className="continuity-grid">
      <div className="continuity-card"><small>الوضع</small><h3>{overview.state?.mode}</h3><p>{overview.state?.reason}</p></div>
      <div className="continuity-card"><small>المصالحة</small><h3>{overview.latest_reconciliation?.status ?? "لم تُشغّل"}</h3><p>{overview.state?.reconciliation_required ? "مطلوبة قبل إعادة الفتح" : "لا توجد مصالحة معلقة"}</p></div>
      <div className="continuity-card"><small>حوادث SEV-1 المفتوحة</small><h3>{overview.open_sev1 ?? 0}</h3></div>
    </div> : null}
  </section>;
}
