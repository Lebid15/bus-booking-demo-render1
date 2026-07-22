"use client";

import Image from "next/image";
import { FormEvent, useState } from "react";

import { browserApiUrl } from "@/lib/public-api";

type Ticket = {
  id: string;
  version: number;
  status: string;
  qr_data: string;
  seat_code: string;
  pdf_url: string | null;
};

type PaymentIntent = {
  id: string;
  method_type: string;
  status: string;
  amount: string;
  currency: string;
  provider_action: Record<string, unknown> | null;
  expires_at: string | null;
};

type ManagedPassenger = {
  id: string;
  full_name: string;
  seat_code: string | null;
  boarding_status: string;
  status: string;
  ticket: Ticket | null;
};


type TripChange = {
  change_id: string;
  change_type: string;
  classification: string;
  status: string;
  response_deadline_at: string | null;
  previous_snapshot: Record<string, unknown>;
  new_snapshot: Record<string, unknown>;
};

type ManagedBooking = {
  id: string;
  pnr: string;
  status: string;
  payment_status: string;
  manage_token: string;
  payment_methods: string[];
  outstanding_amount: string;
  payment_deadline_at: string | null;
  trip: {
    departure_at: string;
    origin: { name: string };
    destination: { name: string };
    office: { name: string };
  };
  passengers: ManagedPassenger[];
  pricing: { total: { amount: string; currency: string } };
  trip_changes: TripChange[];
};


type SupportCaseSummary = {
  id: string;
  priority: string;
  category: string;
  status: string;
  sla_due_at: string | null;
};

type CancellationQuote = {
  allowed: boolean;
  refund_amount: { amount: string; currency: string };
  retained_amount: { amount: string; currency: string };
  expires_at: string;
  quote_token: string;
  passengers: Array<{
    passenger_id: string;
    full_name: string;
    seat_code: string;
    total_amount: string;
    refund_amount: string;
    retained_amount: string;
  }>;
};

const paymentLabels: Record<string, string> = {
  office_cash: "الدفع في المكتب",
  manual_transfer: "تحويل يدوي",
  electronic: "دفع إلكتروني",
};

function localDateTimeValue() {
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
  return now.toISOString().slice(0, 16);
}

function apiErrorMessage(payload: unknown, fallback: string) {
  if (
    typeof payload === "object"
    && payload !== null
    && "error" in payload
    && typeof payload.error === "object"
    && payload.error !== null
    && "message" in payload.error
    && typeof payload.error.message === "string"
  ) {
    return payload.error.message;
  }
  return fallback;
}

export function BookingManager({ initialPnr = "" }: { initialPnr?: string }) {
  const [pnr, setPnr] = useState(initialPnr);
  const [verifier, setVerifier] = useState("");
  const [booking, setBooking] = useState<ManagedBooking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("manual_transfer");
  const [intent, setIntent] = useState<PaymentIntent | null>(null);
  const [transferReference, setTransferReference] = useState("");
  const [senderReference, setSenderReference] = useState("");
  const [proofFileId, setProofFileId] = useState("");
  const [transferredAt, setTransferredAt] = useState(localDateTimeValue());
  const [paymentMessage, setPaymentMessage] = useState<string | null>(null);
  const [selectedPassengerIds, setSelectedPassengerIds] = useState<string[]>([]);
  const [cancellationQuote, setCancellationQuote] = useState<CancellationQuote | null>(null);
  const [cancellationMessage, setCancellationMessage] = useState<string | null>(null);
  const [tripChangeMessage, setTripChangeMessage] = useState<string | null>(null);
  const [supportCategory, setSupportCategory] = useState("office_not_responding");
  const [supportPriority, setSupportPriority] = useState("P2");
  const [supportBody, setSupportBody] = useState("");
  const [supportCase, setSupportCase] = useState<SupportCaseSummary | null>(null);

  function storeBooking(payload: ManagedBooking, manageToken?: string) {
    const normalized = {
      ...payload,
      manage_token: manageToken ?? payload.manage_token,
    };
    setBooking(normalized);
    setSelectedPassengerIds(
      normalized.passengers.filter((passenger) => passenger.status === "active").map((passenger) => passenger.id),
    );
  }

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = await fetch(browserApiUrl("/v1/public/bookings/lookup"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({ pnr: pnr.trim(), contact_verifier: verifier.trim() }),
      });
      const payload = await response.json() as ManagedBooking | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("pnr" in payload)) {
        setBooking(null);
        setError("تعذر العثور على الحجز بهذه البيانات. تحقق من PNR ووسيلة الاتصال.");
        return;
      }
      const managed = payload as ManagedBooking;
      storeBooking(managed);
      setPaymentMethod(managed.payment_methods[0] ?? "office_cash");
      setIntent(null);
      setPaymentMessage(null);
      setCancellationQuote(null);
      setCancellationMessage(null);
      setTripChangeMessage(null);
    } catch {
      setError("تعذر الاتصال بالخادم حاليًا.");
    } finally {
      setLoading(false);
    }
  }

  async function startPayment() {
    if (!booking) return;
    setError(null);
    setPaymentMessage(null);
    setLoading(true);
    try {
      const query = new URLSearchParams({ manage_token: booking.manage_token });
      const response = await fetch(
        browserApiUrl(`/v1/public/bookings/${booking.pnr}/payments?${query}`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify({
            method_type: paymentMethod,
            return_url: `${window.location.origin}/manage-booking?pnr=${booking.pnr}`,
          }),
        },
      );
      const payload = await response.json() as PaymentIntent | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) {
        setError(apiErrorMessage(payload, "تعذر بدء عملية الدفع."));
        return;
      }
      const paymentIntent = payload as PaymentIntent;
      setIntent(paymentIntent);
      if (paymentIntent.method_type === "office_cash") {
        setPaymentMessage("تم تثبيت مبلغ الدفع. ادفع في المكتب قبل المهلة واحتفظ بالإيصال.");
      } else if (paymentIntent.method_type === "electronic") {
        const target = paymentIntent.provider_action?.url;
        setPaymentMessage(
          typeof target === "string"
            ? "تم إنشاء جلسة دفع مستضافة. افتح رابط المزود لإكمالها."
            : "جلسة الدفع الإلكترونية قيد التجهيز.",
        );
      }
    } catch {
      setError("تعذر الاتصال بخدمة الدفع.");
    } finally {
      setLoading(false);
    }
  }

  async function submitTransfer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!booking || !intent) return;
    setError(null);
    setLoading(true);
    try {
      const response = await fetch(
        browserApiUrl(`/v1/public/payment-intents/${intent.id}/manual-transfer`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify({
            transfer_reference: transferReference.trim(),
            transferred_at: new Date(transferredAt).toISOString(),
            amount: intent.amount,
            sender_reference: senderReference.trim() || null,
            proof_file_id: proofFileId.trim() || null,
          }),
        },
      );
      const payload = await response.json() as PaymentIntent | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) {
        setError(apiErrorMessage(payload, "تعذر إرسال إثبات التحويل."));
        return;
      }
      setIntent(payload as PaymentIntent);
      setBooking({ ...booking, payment_status: "pending_verification" });
      setPaymentMessage("تم إرسال بيانات التحويل للمراجعة. لا تُصدر التذكرة قبل اعتماد وصول المبلغ.");
    } catch {
      setError("تعذر إرسال بيانات التحويل حاليًا.");
    } finally {
      setLoading(false);
    }
  }

  function togglePassenger(passengerId: string) {
    setCancellationQuote(null);
    setCancellationMessage(null);
    setSelectedPassengerIds((current) => (
      current.includes(passengerId)
        ? current.filter((id) => id !== passengerId)
        : [...current, passengerId]
    ));
  }

  async function requestCancellationQuote() {
    if (!booking || selectedPassengerIds.length === 0) return;
    setError(null);
    setCancellationMessage(null);
    setLoading(true);
    try {
      const query = new URLSearchParams({ manage_token: booking.manage_token });
      selectedPassengerIds.forEach((passengerId) => query.append("passenger_id", passengerId));
      const response = await fetch(
        browserApiUrl(`/v1/public/bookings/${booking.pnr}/cancellation-quote?${query}`),
        { cache: "no-store" },
      );
      const payload = await response.json() as CancellationQuote | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("quote_token" in payload)) {
        setError(apiErrorMessage(payload, "تعذر حساب عرض الإلغاء."));
        return;
      }
      setCancellationQuote(payload as CancellationQuote);
    } catch {
      setError("تعذر الاتصال بخدمة الإلغاء.");
    } finally {
      setLoading(false);
    }
  }

  async function respondToTripChange(changeId: string, choice: "accept" | "alternative" | "refund") {
    if (!booking) return;
    setError(null);
    setTripChangeMessage(null);
    setLoading(true);
    try {
      const query = new URLSearchParams({ manage_token: booking.manage_token });
      const response = await fetch(
        browserApiUrl(`/v1/public/bookings/${booking.pnr}/trip-changes/${changeId}/respond?${query}`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify({ choice }),
        },
      );
      const payload = await response.json() as { status?: string } | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("status" in payload)) {
        setError(apiErrorMessage(payload, "تعذر تسجيل ردك على تغيير الرحلة."));
        return;
      }
      const status = String(payload.status);
      setBooking({
        ...booking,
        trip_changes: booking.trip_changes.map((item) => (
          item.change_id === changeId ? { ...item, status } : item
        )),
      });
      setTripChangeMessage(
        choice === "accept"
          ? "تم قبول التغيير وتثبيت المقعد الجديد."
          : choice === "alternative"
            ? "تم إرسال طلب رحلة بديلة إلى المكتب."
            : "تم إرسال طلب الاسترداد الناتج عن التغيير.",
      );
    } catch {
      setError("تعذر الاتصال بخدمة تغييرات الرحلة.");
    } finally {
      setLoading(false);
    }
  }

  async function openSupportCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!booking || !supportBody.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const query = new URLSearchParams({ manage_token: booking.manage_token });
      const response = await fetch(
        browserApiUrl(`/v1/public/bookings/${booking.pnr}/support-cases?${query}`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify({
            category: supportCategory,
            priority: supportPriority,
            message: supportBody.trim(),
            attachments: [],
          }),
        },
      );
      const payload = await response.json() as SupportCaseSummary | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("id" in payload)) {
        setError(apiErrorMessage(payload, "تعذر فتح حالة الدعم."));
        return;
      }
      setSupportCase(payload as SupportCaseSummary);
      setSupportBody("");
    } catch {
      setError("تعذر الاتصال بخدمة الدعم.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmCancellation() {
    if (!booking || !cancellationQuote) return;
    setError(null);
    setLoading(true);
    try {
      const query = new URLSearchParams({ manage_token: booking.manage_token });
      const response = await fetch(
        browserApiUrl(`/v1/public/bookings/${booking.pnr}/cancel?${query}`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify({
            quote_token: cancellationQuote.quote_token,
            reason_code: "customer_request",
          }),
        },
      );
      const payload = await response.json() as ManagedBooking | unknown;
      if (!response.ok || typeof payload !== "object" || payload === null || !("pnr" in payload)) {
        setError(apiErrorMessage(payload, "تعذر تنفيذ الإلغاء."));
        return;
      }
      const refundAmount = cancellationQuote.refund_amount.amount;
      storeBooking(payload as ManagedBooking, booking.manage_token);
      setCancellationQuote(null);
      setCancellationMessage(
        Number(refundAmount) > 0
          ? `تم إلغاء الركاب المحددين وفتح طلب استرداد بقيمة ${refundAmount} ${booking.pricing.total.currency}.`
          : "تم إلغاء الركاب المحددين وتحرير المقاعد.",
      );
    } catch {
      setError("تعذر تنفيذ الإلغاء حاليًا.");
    } finally {
      setLoading(false);
    }
  }

  if (booking) {
    const payable = !["paid", "refunded"].includes(booking.payment_status)
      && Number(booking.outstanding_amount) > 0;
    const activePassengers = booking.passengers.filter((passenger) => passenger.status === "active");
    const cancellable = ["confirmed", "awaiting_payment"].includes(booking.status)
      && activePassengers.length > 0;
    return (
      <section className="workspace-panel booking-manage-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">إدارة الحجز</p>
            <h2><bdi dir="ltr">{booking.pnr}</bdi></h2>
          </div>
          <span className="state-badge state-active">{booking.status}</span>
        </div>
        <div className="success-grid">
          <div><span>المسار</span><strong>{booking.trip.origin.name} ← {booking.trip.destination.name}</strong></div>
          <div><span>المكتب</span><strong>{booking.trip.office.name}</strong></div>
          <div><span>حالة الدفع</span><strong>{booking.payment_status}</strong></div>
          <div><span>الإجمالي الحالي</span><strong>{booking.pricing.total.amount} {booking.pricing.total.currency}</strong></div>
        </div>

        {booking.trip_changes.length > 0 ? (
          <section className="trip-change-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">تغيير جوهري في الرحلة</p>
                <h3>اختر قبول التغيير أو طلب بديل أو استرداد</h3>
              </div>
              <span className="state-badge state-pending">حق المسافر محفوظ</span>
            </div>
            <div className="trip-change-list">
              {booking.trip_changes.map((change) => (
                <article className="trip-change-card" key={change.change_id}>
                  <div className="section-heading">
                    <div>
                      <h4>{change.change_type} · {change.classification}</h4>
                      <small>الحالة: {change.status}</small>
                    </div>
                    {change.response_deadline_at ? (
                      <span className="state-badge state-pending">
                        حتى {new Date(change.response_deadline_at).toLocaleString("ar")}
                      </span>
                    ) : null}
                  </div>
                  {change.status === "pending" ? (
                    <div className="action-row">
                      <button type="button" disabled={loading} onClick={() => respondToTripChange(change.change_id, "accept")}>قبول</button>
                      <button className="secondary-button" type="button" disabled={loading} onClick={() => respondToTripChange(change.change_id, "alternative")}>طلب بديل</button>
                      <button className="secondary-button" type="button" disabled={loading} onClick={() => respondToTripChange(change.change_id, "refund")}>طلب استرداد</button>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
            {tripChangeMessage ? <p className="hold-success">{tripChangeMessage}</p> : null}
          </section>
        ) : null}

        {payable ? (
          <section className="payment-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">إكمال الدفع</p>
                <h3>{booking.outstanding_amount} {booking.pricing.total.currency}</h3>
              </div>
              {booking.payment_deadline_at ? (
                <span className="state-badge state-pending">
                  قبل {new Date(booking.payment_deadline_at).toLocaleString("ar")}
                </span>
              ) : null}
            </div>
            {!intent ? (
              <div className="payment-method-row">
                <label>
                  طريقة الدفع
                  <select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}>
                    {booking.payment_methods.map((method) => (
                      <option value={method} key={method}>{paymentLabels[method] ?? method}</option>
                    ))}
                  </select>
                </label>
                <button type="button" disabled={loading} onClick={startPayment}>
                  {loading ? "جارٍ البدء..." : "متابعة الدفع"}
                </button>
              </div>
            ) : null}

            {intent?.method_type === "manual_transfer" && intent.status !== "pending_verification" ? (
              <form className="stack-form manual-transfer-form" onSubmit={submitTransfer}>
                <label>
                  مرجع التحويل
                  <input required maxLength={160} dir="ltr" value={transferReference} onChange={(event) => setTransferReference(event.target.value)} />
                </label>
                <label>
                  وقت التحويل الفعلي
                  <input required type="datetime-local" value={transferredAt} onChange={(event) => setTransferredAt(event.target.value)} />
                </label>
                <label>
                  اسم أو مرجع المرسل
                  <input maxLength={160} value={senderReference} onChange={(event) => setSenderReference(event.target.value)} />
                </label>
                <label>
                  معرف ملف الإثبات الخاص
                  <input maxLength={500} dir="ltr" value={proofFileId} onChange={(event) => setProofFileId(event.target.value)} placeholder="private-upload-id" />
                </label>
                <button type="submit" disabled={loading}>{loading ? "جارٍ الإرسال..." : "إرسال للتحقق"}</button>
                <p className="form-note">الصورة وحدها لا تعد تأكيدًا؛ يراجع المكتب المرجع والمبلغ ووقت التحويل.</p>
              </form>
            ) : null}

            {intent?.method_type === "electronic" && typeof intent.provider_action?.url === "string" ? (
              <a className="primary-link" href={intent.provider_action.url} rel="noreferrer">فتح صفحة مزود الدفع</a>
            ) : null}
            {paymentMessage ? <p className="hold-success">{paymentMessage}</p> : null}
          </section>
        ) : null}

        <section className="trip-change-panel support-request-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">الدعم وحقوق المسافر</p>
              <h3>فتح حالة مرتبطة بالحجز والرحلة</h3>
            </div>
            <span className="state-badge state-active">SLA محكوم</span>
          </div>
          {supportCase ? (
            <div className="hold-success">
              تم فتح الحالة <bdi dir="ltr">{supportCase.id}</bdi> بالأولوية {supportCase.priority} وحالتها {supportCase.status}.
            </div>
          ) : (
            <form className="stack-form" onSubmit={openSupportCase}>
              <label>
                نوع المشكلة
                <select value={supportCategory} onChange={(event) => setSupportCategory(event.target.value)}>
                  <option value="office_not_responding">المكتب لا يجيب</option>
                  <option value="trip_change_dispute">اعتراض على تغيير الرحلة</option>
                  <option value="boarding_denial">مشكلة أثناء الصعود</option>
                  <option value="service_interruption">توقف الخدمة</option>
                </select>
              </label>
              <label>
                الأولوية
                <select value={supportPriority} onChange={(event) => setSupportPriority(event.target.value)}>
                  <option value="P1">P1 — عاجل قبل الرحلة</option>
                  <option value="P2">P2 — مرتفع</option>
                  <option value="P3">P3 — عادي</option>
                  <option value="P4">P4 — منخفض</option>
                </select>
              </label>
              <label>
                التفاصيل
                <textarea rows={4} required value={supportBody} onChange={(event) => setSupportBody(event.target.value)} />
              </label>
              <button disabled={loading}>فتح حالة دعم</button>
            </form>
          )}
        </section>

        {cancellable ? (
          <section className="cancellation-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">الإلغاء والاسترداد</p>
                <h3>اختر الركاب المطلوب إلغاؤهم</h3>
              </div>
              <span className="state-badge state-pending">الحساب من سياسة الحجز المثبتة</span>
            </div>
            <div className="cancellation-passengers">
              {activePassengers.map((passenger) => (
                <label className="cancellation-passenger" key={passenger.id}>
                  <input
                    type="checkbox"
                    checked={selectedPassengerIds.includes(passenger.id)}
                    onChange={() => togglePassenger(passenger.id)}
                  />
                  <span>
                    <strong>{passenger.full_name}</strong>
                    <small>المقعد {passenger.seat_code ?? "—"}</small>
                  </span>
                </label>
              ))}
            </div>
            {!cancellationQuote ? (
              <button
                type="button"
                disabled={loading || selectedPassengerIds.length === 0}
                onClick={requestCancellationQuote}
              >
                {loading ? "جارٍ الحساب..." : "حساب مبلغ الإلغاء"}
              </button>
            ) : (
              <div className="cancellation-quote">
                <div>
                  <span>المبلغ المتوقع استرداده</span>
                  <strong>{cancellationQuote.refund_amount.amount} {cancellationQuote.refund_amount.currency}</strong>
                </div>
                <div>
                  <span>المبلغ المحتفظ به حسب السياسة</span>
                  <strong>{cancellationQuote.retained_amount.amount} {cancellationQuote.retained_amount.currency}</strong>
                </div>
                <small>العرض صالح حتى {new Date(cancellationQuote.expires_at).toLocaleString("ar")}</small>
                <div className="action-row">
                  <button type="button" disabled={loading} onClick={confirmCancellation}>
                    {loading ? "جارٍ التنفيذ..." : "تأكيد الإلغاء"}
                  </button>
                  <button className="secondary-button" type="button" onClick={() => setCancellationQuote(null)}>
                    تعديل الاختيار
                  </button>
                </div>
              </div>
            )}
            {cancellationMessage ? <p className="hold-success">{cancellationMessage}</p> : null}
          </section>
        ) : null}

        {error ? <p className="error-message" role="alert">{error}</p> : null}
        <div className="ticket-list">
          {booking.passengers.map((passenger) => (
            <article className="ticket-card expanded-ticket" key={passenger.id}>
              <div>
                <small>المسافر</small>
                <strong>{passenger.full_name}</strong>
                <span>
                  {passenger.status === "cancelled"
                    ? "ملغى · تم تحرير المقعد"
                    : `المقعد ${passenger.seat_code ?? "—"} · ${passenger.boarding_status}`}
                </span>
              </div>
              {passenger.ticket ? (
                <>
                  <Image
                    className="ticket-qr"
                    alt={`QR تذكرة ${passenger.full_name}`}
                    width={112}
                    height={112}
                    unoptimized
                    src={browserApiUrl(`/v1/public/tickets/${passenger.ticket.id}/qr.svg?pnr=${encodeURIComponent(booking.pnr)}&manage_token=${encodeURIComponent(booking.manage_token)}`)}
                  />
                  <a
                    className="primary-link"
                    target="_blank"
                    rel="noreferrer"
                    href={browserApiUrl(`${passenger.ticket.pdf_url}?manage_token=${encodeURIComponent(booking.manage_token)}`)}
                  >
                    طباعة أو حفظ PDF
                  </a>
                </>
              ) : (
                <span className={`state-badge ${passenger.status === "cancelled" ? "state-cancelled" : "state-pending"}`}>
                  {passenger.status === "cancelled" ? "التذكرة مبطلة" : "التذكرة بانتظار تأكيد الحجز"}
                </span>
              )}
            </article>
          ))}
        </div>
        <button type="button" onClick={() => setBooking(null)}>استرجاع حجز آخر</button>
      </section>
    );
  }

  return (
    <form className="narrow-card stack-form" onSubmit={lookup}>
      <label>
        رقم الحجز PNR
        <input value={pnr} dir="ltr" minLength={6} maxLength={12} required onChange={(event) => setPnr(event.target.value.toUpperCase())} />
      </label>
      <label>
        رقم الهاتف أو البريد المستخدم بالحجز
        <input value={verifier} dir="ltr" minLength={4} required onChange={(event) => setVerifier(event.target.value)} />
      </label>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
      <button type="submit" disabled={loading}>{loading ? "جارٍ التحقق..." : "عرض الحجز"}</button>
      <p className="form-note">نستخدم البيانات للتحقق فقط، ولا نكشف إن كان PNR موجودًا عند إدخال معلومات خاطئة.</p>
    </form>
  );
}
