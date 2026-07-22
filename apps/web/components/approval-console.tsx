"use client";

import { useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type Approval = {
  public_id: string;
  action_type: string;
  target_type: string;
  target_id: string;
  payload: Record<string, unknown>;
  risk_level: string;
  status: string;
  reason: string;
  requested_by: string;
  approved_by: string | null;
  requested_at: string;
};

function headers(token: string, mutation = false): HeadersInit {
  return {
    Authorization: `Bearer ${token.trim()}`,
    ...(mutation
      ? { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }
      : {}),
  };
}

function errorMessage(payload: unknown): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "error" in payload &&
    typeof payload.error === "object" &&
    payload.error !== null &&
    "message" in payload.error &&
    typeof payload.error.message === "string"
  ) {
    return payload.error.message;
  }
  return "تعذر تنفيذ العملية.";
}

export function ApprovalConsole() {
  const [token, setToken] = useStoredAccessToken();
  const [rows, setRows] = useState<Approval[]>([]);
  const [reason, setReason] = useState("تمت مراجعة التصنيف والأثر على الحجوزات القائمة");
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    const response = await fetch(browserApiUrl("/v1/platform/approvals?status=pending"), {
      headers: headers(token),
    });
    const payload = (await response.json()) as Approval[] | unknown;
    if (!response.ok || !Array.isArray(payload)) {
      setMessage(errorMessage(payload));
      return;
    }
    setRows(payload);
    setMessage(`يوجد ${payload.length} طلب اعتماد معلّق.`);
  }

  async function command(id: string, action: "approve" | "reject") {
    const response = await fetch(browserApiUrl(`/v1/platform/approvals/${id}/commands`), {
      method: "POST",
      headers: headers(token, true),
      body: JSON.stringify({ command: action, reason }),
    });
    const payload = (await response.json()) as unknown;
    if (!response.ok) {
      setMessage(errorMessage(payload));
      return;
    }
    setMessage(action === "approve" ? "تم الاعتماد والتنفيذ بواسطة المراجع الثاني." : "تم رفض الطلب.");
    await load();
  }

  return (
    <section className="workspace-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Dual control</p>
          <h2>طابور الاعتماد المزدوج</h2>
        </div>
        <button onClick={load}>تحديث</button>
      </div>
      <div className="stack-form notification-filters">
        <label>
          جلسة المراجع مع MFA حديث
          <input type="password" value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
        <label>
          سبب القرار
          <textarea minLength={10} value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
      </div>
      <div className="data-table">
        {rows.map((item) => (
          <div className="data-row" key={item.public_id}>
            <div>
              <strong>{item.action_type}</strong>
              <small>
                {item.target_type}:{item.target_id} · طالب القرار {item.requested_by}
              </small>
              <small>{item.reason}</small>
            </div>
            <span className="state-badge state-pending">{item.risk_level}</span>
            <div className="button-row">
              <button onClick={() => command(item.public_id, "approve")}>اعتماد</button>
              <button className="secondary-button" onClick={() => command(item.public_id, "reject")}>
                رفض
              </button>
            </div>
          </div>
        ))}
      </div>
      {rows.length === 0 ? (
        <div className="empty-state">
          <p>لا توجد طلبات اعتماد معلّقة بعد التحميل.</p>
        </div>
      ) : null}
      {message ? <p className="form-note">{message}</p> : null}
    </section>
  );
}
