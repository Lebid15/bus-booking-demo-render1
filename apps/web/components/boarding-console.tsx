"use client";

import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";
import { useStoredAccessToken } from "@/lib/auth";

type ManifestPassenger = {
  passenger_id: string;
  pnr: string;
  full_name: string;
  identity_tail: string | null;
  seat_code: string | null;
  boarding_status: string;
  ticket_status: string | null;
};

type ManifestPayload = {
  version: number;
  status: string;
  sha256: string;
  generated_at: string;
  manifest: {
    trip_id: string;
    trip_version: number;
    scheduled_departure_at: string;
    passengers: ManifestPassenger[];
  };
};

type BoardingResult = {
  passenger_id: string;
  boarding_status: string;
  ticket_status: string | null;
};

type OfflinePackage = {
  download_url: string;
  expires_at: string;
  package_hash: string;
};

type OfflineSyncResult = {
  accepted: number;
  duplicates: number;
  conflicts: Array<{ offline_event_id?: string; type?: string; conflict_id?: string }>;
  purge_required: boolean;
};

function errorMessage(payload: unknown) {
  if (
    typeof payload === "object"
    && payload !== null
    && "error" in payload
    && typeof payload.error === "object"
    && payload.error !== null
    && "message" in payload.error
    && typeof payload.error.message === "string"
  ) return payload.error.message;
  return "تعذر إكمال العملية.";
}

export function BoardingConsole() {
  const [accessToken, setAccessToken] = useStoredAccessToken();
  const [tripId, setTripId] = useState("");
  const [ticketQr, setTicketQr] = useState("");
  const [passengerId, setPassengerId] = useState("");
  const [reason, setReason] = useState("");
  const [manifest, setManifest] = useState<ManifestPayload | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [offlinePackage, setOfflinePackage] = useState<OfflinePackage | null>(null);
  const [offlineEvents, setOfflineEvents] = useState("[]");
  const [offlineResult, setOfflineResult] = useState<OfflineSyncResult | null>(null);
  const [loading, setLoading] = useState(false);

  function headers(mutation = false) {
    return {
      Authorization: `Bearer ${accessToken.trim()}`,
      ...(mutation ? {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      } : {}),
    };
  }

  async function loadManifest() {
    if (!tripId.trim() || !accessToken.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(
        browserApiUrl(`/v1/office/trips/${encodeURIComponent(tripId.trim())}/manifest`),
        { headers: headers() },
      );
      const payload = await response.json() as ManifestPayload | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("manifest" in payload)) {
        setMessage(errorMessage(payload));
        return;
      }
      setManifest(payload as ManifestPayload);
      setMessage("تم تحديث Manifest والتحقق من بصمته.");
    } catch {
      setMessage("تعذر الاتصال بخادم التشغيل.");
    } finally {
      setLoading(false);
    }
  }

  async function submitBoarding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tripId.trim() || !accessToken.trim()) return;
    setLoading(true);
    setMessage(null);
    const manual = !ticketQr.trim();
    try {
      const response = await fetch(
        browserApiUrl(`/v1/office/trips/${encodeURIComponent(tripId.trim())}/boarding`),
        {
          method: "POST",
          headers: headers(true),
          body: JSON.stringify({
            command: "board",
            ticket_qr: manual ? null : ticketQr.trim(),
            passenger_id: manual ? passengerId.trim() : null,
            reason_code: manual ? reason.trim() : null,
          }),
        },
      );
      const payload = await response.json() as BoardingResult | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("boarding_status" in payload)) {
        setMessage(errorMessage(payload));
        return;
      }
      const result = payload as BoardingResult;
      setMessage(`تم تسجيل حالة الراكب: ${result.boarding_status}`);
      setTicketQr("");
      await loadManifest();
    } catch {
      setMessage("تعذر الاتصال بخادم التشغيل.");
    } finally {
      setLoading(false);
    }
  }

  async function generateOfflinePackage() {
    if (!tripId.trim() || !accessToken.trim()) return;
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(
        browserApiUrl(`/v1/office/trips/${encodeURIComponent(tripId.trim())}/offline-package`),
        { method: "POST", headers: headers(true) },
      );
      const payload = await response.json() as OfflinePackage | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("package_hash" in payload)) {
        setMessage(errorMessage(payload));
        return;
      }
      setOfflinePackage(payload as OfflinePackage);
      setMessage("تم إنشاء حزمة مشفرة وموقعة لهذا الجهاز.");
    } catch {
      setMessage("تعذر إنشاء حزمة العمل دون اتصال.");
    } finally {
      setLoading(false);
    }
  }

  async function syncOfflineQueue() {
    if (!tripId.trim() || !accessToken.trim() || !offlinePackage) return;
    setLoading(true);
    setMessage(null);
    try {
      const parsed = JSON.parse(offlineEvents) as unknown;
      if (!Array.isArray(parsed)) {
        setMessage("يجب أن تكون قائمة الأحداث مصفوفة JSON.");
        return;
      }
      const response = await fetch(
        browserApiUrl(`/v1/office/trips/${encodeURIComponent(tripId.trim())}/offline-sync`),
        {
          method: "POST",
          headers: headers(true),
          body: JSON.stringify({ package_hash: offlinePackage.package_hash, events: parsed }),
        },
      );
      const payload = await response.json() as OfflineSyncResult | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("accepted" in payload)) {
        setMessage(errorMessage(payload));
        return;
      }
      setOfflineResult(payload as OfflineSyncResult);
      setMessage("اكتملت المزامنة؛ احتفظت المنصة بأي تعارض للمراجعة.");
      await loadManifest();
    } catch (error) {
      setMessage(error instanceof SyntaxError ? "صيغة أحداث JSON غير صالحة." : "تعذرت مزامنة الأحداث.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="boarding-workspace">
      <article className="workspace-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">بوابة الصعود</p>
            <h2>مسح QR أو تحقق يدوي</h2>
          </div>
          <span className="state-badge state-active">أحادي الاستخدام</span>
        </div>
        <div className="stack-form boarding-credentials">
          <label>
            رمز جلسة موظف المكتب
            <input value={accessToken} onChange={(event) => setAccessToken(event.target.value)} type="password" />
          </label>
          <label>
            رقم الرحلة العام
            <input value={tripId} onChange={(event) => setTripId(event.target.value)} placeholder="Trip public ID" />
          </label>
          <button type="button" className="secondary-button" onClick={loadManifest} disabled={loading}>
            تحديث Manifest
          </button>
        </div>
        <form className="stack-form boarding-form" onSubmit={submitBoarding}>
          <label>
            بيانات QR
            <textarea value={ticketQr} onChange={(event) => setTicketQr(event.target.value)} rows={4} placeholder="tq1.…" />
          </label>
          <div className="manual-check-box">
            <strong>التحقق اليدوي عند تعطل QR</strong>
            <label>
              معرف الراكب
              <input value={passengerId} onChange={(event) => setPassengerId(event.target.value)} />
            </label>
            <label>
              سبب التحقق اليدوي
              <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="تمت مطابقة الهوية" />
            </label>
          </div>
          <button type="submit" disabled={loading || (!ticketQr.trim() && (!passengerId.trim() || !reason.trim()))}>
            {loading ? "جارٍ التحقق…" : "تسجيل الصعود"}
          </button>
          {message ? <p className="form-note">{message}</p> : null}
        </form>
      </article>

      <article className="workspace-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Manifest محكوم</p>
            <h2>قائمة الركاب وحالة الصعود</h2>
          </div>
          {manifest ? <span className="state-badge state-active">v{manifest.version}</span> : null}
        </div>
        {manifest ? (
          <>
            <div className="manifest-meta">
              <span>SHA-256</span>
              <code>{manifest.sha256}</code>
            </div>
            <div className="data-table">
              {manifest.manifest.passengers.map((passenger) => (
                <div className="data-row manifest-row" key={passenger.passenger_id}>
                  <div>
                    <strong>{passenger.full_name}</strong>
                    <small>{passenger.pnr} · المقعد {passenger.seat_code ?? "—"}</small>
                  </div>
                  <span className={`state-badge ${passenger.boarding_status === "boarded" ? "state-active" : "state-pending"}`}>
                    {passenger.boarding_status}
                  </span>
                  <button type="button" className="text-button" onClick={() => setPassengerId(passenger.passenger_id)}>
                    تحقق يدوي
                  </button>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-state">
            <h3>لم يتم تحميل القائمة بعد</h3>
            <p>أدخل جلسة الموظف ورقم الرحلة ثم حدّث Manifest.</p>
          </div>
        )}
      </article>

      <article className="workspace-panel boarding-offline-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">وضع دون اتصال</p>
            <h2>حزمة الجهاز ومزامنة الطابور</h2>
          </div>
          <span className="state-badge state-pending">MFA + جهاز موثوق</span>
        </div>
        <p className="form-note">
          الحزمة مشفرة وموقعة ومحدودة المدة. لا تسمح إلا بأحداث الوصول والتحقق والصعود، وتحتفظ بالتعارضات للمراجعة.
        </p>
        <div className="stack-form">
          <button type="button" className="secondary-button" onClick={generateOfflinePackage} disabled={loading}>
            إنشاء حزمة دون اتصال
          </button>
          {offlinePackage ? (
            <div className="manifest-meta">
              <span>بصمة الحزمة</span>
              <code>{offlinePackage.package_hash}</code>
              <small>تنتهي: {new Date(offlinePackage.expires_at).toLocaleString("ar")}</small>
              <a className="secondary-button" href={offlinePackage.download_url} download={`boarding-${tripId}.bin`}>
                تنزيل الحزمة المشفرة
              </a>
            </div>
          ) : null}
          <label>
            أحداث الجهاز بصيغة JSON
            <textarea
              value={offlineEvents}
              onChange={(event) => setOfflineEvents(event.target.value)}
              rows={8}
              placeholder='[{"offline_event_id":"device-001","command":"board","ticket_qr":"tq1.…"}]'
            />
          </label>
          <button type="button" onClick={syncOfflineQueue} disabled={loading || !offlinePackage}>
            مزامنة الأحداث
          </button>
          {offlineResult ? (
            <div className="status-banner status-success">
              <strong>مقبول: {offlineResult.accepted} · مكرر: {offlineResult.duplicates}</strong>
              <span>تعارضات تحتاج مراجعة: {offlineResult.conflicts.length}</span>
            </div>
          ) : null}
        </div>
      </article>
    </section>
  );
}
