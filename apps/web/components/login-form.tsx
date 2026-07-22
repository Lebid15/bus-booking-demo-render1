"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { storeAuthSession, type AuthSession } from "@/lib/auth";
import { browserApiUrl } from "@/lib/public-api";

type ApiError = {
  error?: {
    code?: string;
    message?: string;
    details?: { challenge_id?: string } | unknown;
  };
};

const demoAccounts = [
  { label: "مدير المنصة", identifier: "admin@demo.local", password: "DemoAdmin!2026" },
  { label: "مالك المكتب", identifier: "office@demo.local", password: "DemoOffice!2026" },
  { label: "موظف الحجوزات", identifier: "agent@demo.local", password: "DemoAgent!2026" },
];

export function LoginForm() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("office@demo.local");
  const [password, setPassword] = useState("DemoOffice!2026");
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const endpoint = challengeId ? "/v1/auth/mfa/verify" : "/v1/auth/login";
      const body = challengeId
        ? { challenge_id: challengeId, code: mfaCode }
        : { identifier: identifier.trim(), password };
      const response = await fetch(browserApiUrl(endpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Device-Label": "متصفح النسخة التجريبية" },
        body: JSON.stringify(body),
      });
      const payload = await response.json() as AuthSession | ApiError;
      if (!response.ok) {
        const error = payload as ApiError;
        const details = error.error?.details;
        if (
          error.error?.code === "AUTH_MFA_REQUIRED"
          && typeof details === "object" && details !== null && "challenge_id" in details
          && typeof details.challenge_id === "string"
        ) {
          setChallengeId(details.challenge_id);
          setMessage("أدخل رمز التحقق الإضافي لإكمال الدخول.");
          return;
        }
        setMessage(error.error?.message ?? "تعذر تسجيل الدخول.");
        return;
      }
      const session = payload as AuthSession;
      storeAuthSession(session);
      router.push(session.landing_path || "/");
      router.refresh();
    } catch {
      setMessage("تعذر الاتصال بالخادم. تأكد أن خدمات Docker تعمل.");
    } finally {
      setLoading(false);
    }
  }

  function selectDemoAccount(account: (typeof demoAccounts)[number]) {
    setIdentifier(account.identifier);
    setPassword(account.password);
    setChallengeId(null);
    setMfaCode("");
    setMessage(null);
  }

  return (
    <div className="workspace-grid login-workspace">
      <section className="narrow-card">
        <form className="stack-form" onSubmit={submit}>
          {!challengeId ? (
            <>
              <label>
                الهاتف أو البريد الإلكتروني
                <input
                  type="text"
                  autoComplete="username"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                />
              </label>
              <label>
                كلمة المرور
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>
            </>
          ) : (
            <label>
              رمز التحقق الإضافي
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={mfaCode}
                onChange={(event) => setMfaCode(event.target.value)}
              />
            </label>
          )}
          <button type="submit" disabled={loading}>{loading ? "جارٍ الدخول…" : "تسجيل الدخول"}</button>
          {message ? <p className="form-note" role="status">{message}</p> : null}
        </form>
      </section>

      <aside className="workspace-panel compact-panel">
        <p className="eyebrow">حسابات النسخة التجريبية</p>
        <h2>اختر الدور الذي تريد تجربته</h2>
        <div className="timeline-list">
          {demoAccounts.map((account) => (
            <button
              type="button"
              className="demo-account-button"
              key={account.identifier}
              onClick={() => selectDemoAccount(account)}
            >
              <strong>{account.label}</strong>
              <bdi dir="ltr">{account.identifier}</bdi>
            </button>
          ))}
        </div>
        <p className="form-note">وضع Demo يعمل محليًا فقط، ويُرفض تلقائيًا في إعداد Production.</p>
      </aside>
    </div>
  );
}
