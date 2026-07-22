"use client";

import { FormEvent, useCallback, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type FinancialEffect = {
  type: "none" | "office_credit" | "office_debit" | "customer_compensation";
  amount: string;
  currency: string;
  ledger_entry_id?: string | null;
};

type Decision = {
  id: string;
  stage: string;
  decision_code: string;
  reasoning: string;
  financial_effect: FinancialEffect;
  appeal_allowed_until: string | null;
  is_final: boolean;
};

type Dispute = {
  id: string;
  booking_id: string;
  office_id: string;
  status: string;
  category: string;
  disputed_amount: string | null;
  currency: string;
  decision_code: string | null;
  decision_summary: string | null;
  appeal_deadline_at: string | null;
  initial_decision: Decision | null;
  appeal: { reason: string; filed_at: string; decided_at: string | null } | null;
  appeal_decision: Decision | null;
  opened_at: string;
};

type Scope = "platform" | "office";

function authHeaders(token: string, mutation = false): HeadersInit {
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

export function DisputeConsole({ scope }: { scope: Scope }) {
  const [token, setToken] = useStoredAccessToken();
  const [statusFilter, setStatusFilter] = useState("");
  const [rows, setRows] = useState<Dispute[]>([]);
  const [selected, setSelected] = useState<Dispute | null>(null);
  const [reasoning, setReasoning] = useState("");
  const [decisionCode, setDecisionCode] = useState("resolved");
  const [effectType, setEffectType] = useState<FinancialEffect["type"]>("none");
  const [amount, setAmount] = useState("0.00");
  const [evidence, setEvidence] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams();
    if (scope === "platform" && statusFilter) query.set("status", statusFilter);
    const response = await fetch(browserApiUrl(`/v1/${scope}/disputes?${query}`), {
      headers: authHeaders(token),
    });
    const payload = (await response.json()) as Dispute[] | unknown;
    if (!response.ok || !Array.isArray(payload)) {
      setMessage(errorMessage(payload));
      return;
    }
    setRows(payload);
    if (selected) {
      setSelected(payload.find((item) => item.id === selected.id) ?? null);
    }
    setMessage(`تم تحميل ${payload.length} نزاعًا.`);
  }, [scope, selected, statusFilter, token]);

  async function platformCommand(command: string) {
    if (!selected) return;
    const body: Record<string, unknown> = { command };
    if (command === "decide" || command === "decide_appeal") {
      body.decision_code = decisionCode;
      body.reasoning = reasoning;
      body.financial_effect = { type: effectType, amount };
    }
    const response = await fetch(browserApiUrl(`/v1/platform/disputes/${selected.id}/commands`), {
      method: "POST",
      headers: authHeaders(token, true),
      body: JSON.stringify(body),
    });
    const payload = (await response.json()) as Dispute | unknown;
    if (!response.ok || typeof payload !== "object" || payload === null) {
      setMessage(errorMessage(payload));
      return;
    }
    setSelected(payload as Dispute);
    setMessage("تم تنفيذ أمر النزاع وتسجيل أثره الرقابي والمالي.");
    await load();
  }

  async function officeSubmit(event: FormEvent<HTMLFormElement>, action: "respond" | "appeal") {
    event.preventDefault();
    if (!selected) return;
    const path = action === "respond" ? "respond" : "appeal";
    const body =
      action === "respond"
        ? { response: reasoning, evidence: { note: evidence } }
        : { reason: reasoning, evidence: evidence ? { note: evidence } : {} };
    const response = await fetch(browserApiUrl(`/v1/office/disputes/${selected.id}/${path}`), {
      method: "POST",
      headers: authHeaders(token, true),
      body: JSON.stringify(body),
    });
    const payload = (await response.json()) as Dispute | unknown;
    if (!response.ok || typeof payload !== "object" || payload === null) {
      setMessage(errorMessage(payload));
      return;
    }
    setSelected(payload as Dispute);
    setMessage(action === "respond" ? "تم إرسال الرد والأدلة." : "تم تقديم الاعتراض ضمن النافذة النظامية.");
    await load();
  }

  return (
    <section className="workspace-grid">
      <article className="workspace-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Dispute governance</p>
            <h2>{scope === "platform" ? "طابور نزاعات المنصة" : "نزاعات المكتب"}</h2>
          </div>
          <button onClick={load}>تحديث</button>
        </div>
        <div className="stack-form">
          <label>
            جلسة {scope === "platform" ? "المنصة" : "المكتب"}
            <input type="password" value={token} onChange={(event) => setToken(event.target.value)} />
          </label>
          {scope === "platform" ? (
            <label>
              الحالة
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">الكل</option>
                {["open", "awaiting_office", "under_review", "decided", "appealed", "closed"].map(
                  (value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ),
                )}
              </select>
            </label>
          ) : null}
        </div>
        <div className="data-table">
          {rows.map((item) => (
            <button className="data-row" key={item.id} onClick={() => setSelected(item)}>
              <div>
                <strong>{item.category}</strong>
                <small>
                  {item.booking_id} · {item.disputed_amount ?? "0.00"} {item.currency}
                </small>
              </div>
              <span className="state-badge state-pending">{item.status}</span>
              <small>{new Date(item.opened_at).toLocaleString("ar")}</small>
            </button>
          ))}
        </div>
      </article>

      <article className="workspace-panel">
        {selected ? (
          <>
            <div className="section-heading">
              <div>
                <p className="eyebrow">{selected.id}</p>
                <h2>{selected.category}</h2>
              </div>
              <span className="state-badge state-active">{selected.status}</span>
            </div>
            <div className="success-grid">
              <div>
                <span>الحجز</span>
                <strong>{selected.booking_id}</strong>
              </div>
              <div>
                <span>المبلغ المتنازع</span>
                <strong>
                  {selected.disputed_amount ?? "0.00"} {selected.currency}
                </strong>
              </div>
            </div>
            {selected.initial_decision ? (
              <div className="status-banner status-success">
                <strong>{selected.initial_decision.decision_code}</strong>
                <span>{selected.initial_decision.reasoning}</span>
                <small>
                  {selected.initial_decision.financial_effect.type} · {selected.initial_decision.financial_effect.amount}{" "}
                  {selected.initial_decision.financial_effect.currency}
                </small>
              </div>
            ) : null}

            {scope === "platform" ? (
              <div className="stack-form">
                <label>
                  رمز القرار
                  <input value={decisionCode} onChange={(event) => setDecisionCode(event.target.value)} />
                </label>
                <label>
                  التسبيب
                  <textarea minLength={10} value={reasoning} onChange={(event) => setReasoning(event.target.value)} />
                </label>
                <label>
                  الأثر المالي
                  <select
                    value={effectType}
                    onChange={(event) => setEffectType(event.target.value as FinancialEffect["type"])}
                  >
                    <option value="none">دون أثر مالي</option>
                    <option value="office_credit">دائن للمكتب</option>
                    <option value="office_debit">مدين على المكتب</option>
                    <option value="customer_compensation">تعويض العميل</option>
                  </select>
                </label>
                <label>
                  المبلغ
                  <input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
                </label>
                <div className="button-row">
                  {selected.status === "open" ? (
                    <button onClick={() => platformCommand("assign_office")}>طلب رد المكتب</button>
                  ) : null}
                  {["open", "under_review"].includes(selected.status) ? (
                    <button onClick={() => platformCommand("decide")}>إصدار القرار الأول</button>
                  ) : null}
                  {selected.status === "appealed" ? (
                    <button onClick={() => platformCommand("decide_appeal")}>قرار الاعتراض النهائي</button>
                  ) : null}
                  {selected.status === "decided" ? (
                    <button className="secondary-button" onClick={() => platformCommand("close_no_appeal")}>
                      إغلاق بعد انتهاء الاعتراض
                    </button>
                  ) : null}
                </div>
              </div>
            ) : (
              <form
                className="stack-form"
                onSubmit={(event) =>
                  officeSubmit(event, selected.status === "awaiting_office" ? "respond" : "appeal")
                }
              >
                <label>
                  {selected.status === "awaiting_office" ? "رد المكتب" : "سبب الاعتراض"}
                  <textarea minLength={10} value={reasoning} onChange={(event) => setReasoning(event.target.value)} />
                </label>
                <label>
                  ملخص الأدلة
                  <textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} />
                </label>
                {selected.status === "awaiting_office" ? <button>إرسال الرد والأدلة</button> : null}
                {selected.status === "decided" ? <button>تقديم اعتراض</button> : null}
              </form>
            )}
          </>
        ) : (
          <div className="empty-state">
            <p>اختر نزاعًا لمراجعة القرار والأثر المالي وحق الاعتراض.</p>
          </div>
        )}
        {message ? <p className="form-note">{message}</p> : null}
      </article>
    </section>
  );
}
