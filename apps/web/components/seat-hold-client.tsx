"use client";

import Link from "next/link";
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { formatMoney, formatTime } from "@/lib/format";
import { browserApiUrl, type PublicTrip, type SeatMap } from "@/lib/public-api";

type PassengerDraft = {
  fullName: string;
  gender: "male" | "female";
  passengerType: "adult" | "child" | "infant";
};

type HoldResponse = {
  hold_token: string;
  expires_at: string;
  quote: {
    subtotal: { amount: string; currency: string };
    discount: { amount: string; currency: string };
    total: { amount: string; currency: string };
    fees: { amount: string; currency: string };
    payment_deadline_at: string | null;
    policy_version_ids: string[];
    quote_version: number;
  };
};

type BookingResponse = {
  id: string;
  pnr: string;
  status: string;
  payment_status: string;
  manage_token: string;
  passengers: Array<{
    id: string;
    full_name: string;
    seat_code: string;
    boarding_status: string;
    ticket: {
      id: string;
      version: number;
      status: string;
      qr_data: string;
      seat_code: string;
      pdf_url: string | null;
    } | null;
  }>;
  pricing: HoldResponse["quote"];
  payment_deadline_at: string | null;
};

type SeatHoldClientProps = {
  trip: PublicTrip;
  initialSeatMap: SeatMap;
  passengerCount: number;
};

const seatStatusLabels: Record<string, string> = {
  available: "متاح",
  held_by_you: "محفوظ لك",
  unavailable: "غير متاح",
  policy_unavailable: "غير متاح حسب السياسة",
  blocked: "محجوب",
};

const seatTypeLabels: Record<string, string> = {
  standard: "عادي",
  vip: "مميز",
  women: "مخصص",
};

const paymentLabels: Record<string, string> = {
  office_cash: "الدفع لاحقًا في المكتب",
  manual_transfer: "تحويل يدوي",
  electronic: "دفع إلكتروني",
};

export function SeatHoldClient({ trip, initialSeatMap, passengerCount }: SeatHoldClientProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const [passengers, setPassengers] = useState<PassengerDraft[]>(
    Array.from({ length: passengerCount }, () => ({
      fullName: "",
      gender: "male",
      passengerType: "adult",
    })),
  );
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [paymentMethod, setPaymentMethod] = useState(trip.payment_methods[0] ?? "office_cash");
  const [acceptedPolicies, setAcceptedPolicies] = useState(false);
  const [hold, setHold] = useState<HoldResponse | null>(null);
  const [booking, setBooking] = useState<BookingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const holdKey = useRef(crypto.randomUUID());
  const bookingKey = useRef(crypto.randomUUID());

  const selectedSeats = useMemo(
    () => selected.map((id) => initialSeatMap.seats.find((seat) => seat.id === id)).filter(Boolean),
    [initialSeatMap.seats, selected],
  );

  const storageKey = `booking-draft:${trip.id}`;

  /* eslint-disable react-hooks/set-state-in-effect -- one-time restoration from sessionStorage */
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (raw) {
        const draft = JSON.parse(raw) as {
          selected?: string[]; passengers?: PassengerDraft[]; contactName?: string; contactPhone?: string;
          contactEmail?: string; paymentMethod?: string; hold?: HoldResponse | null; holdKey?: string; bookingKey?: string;
        };
        if (Array.isArray(draft.selected)) setSelected(draft.selected.slice(0, passengerCount));
        if (Array.isArray(draft.passengers) && draft.passengers.length === passengerCount) setPassengers(draft.passengers);
        setContactName(draft.contactName ?? "");
        setContactPhone(draft.contactPhone ?? "");
        setContactEmail(draft.contactEmail ?? "");
        if (draft.paymentMethod) setPaymentMethod(draft.paymentMethod);
        if (draft.hold && new Date(draft.hold.expires_at).getTime() > Date.now()) setHold(draft.hold);
        if (draft.holdKey) holdKey.current = draft.holdKey;
        if (draft.bookingKey) bookingKey.current = draft.bookingKey;
      }
    } catch {
      sessionStorage.removeItem(storageKey);
    } finally {
      setHydrated(true);
    }
  }, [passengerCount, storageKey]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    if (!hydrated || booking) return;
    sessionStorage.setItem(storageKey, JSON.stringify({
      selected, passengers, contactName, contactPhone, contactEmail, paymentMethod, hold,
      holdKey: holdKey.current, bookingKey: bookingKey.current,
    }));
  }, [booking, contactEmail, contactName, contactPhone, hold, hydrated, passengers, paymentMethod, selected, storageKey]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  function handleSeatKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const buttons = Array.from(
      event.currentTarget.closest(".seat-grid")?.querySelectorAll<HTMLButtonElement>("[data-seat-index]") ?? [],
    );
    if (!buttons.length) return;
    const columns = window.innerWidth <= 620 ? 4 : 4;
    let next = index;
    if (event.key === "ArrowLeft") next = Math.min(buttons.length - 1, index + 1);
    else if (event.key === "ArrowRight") next = Math.max(0, index - 1);
    else if (event.key === "ArrowDown") next = Math.min(buttons.length - 1, index + columns);
    else if (event.key === "ArrowUp") next = Math.max(0, index - columns);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = buttons.length - 1;
    else return;
    event.preventDefault();
    buttons[next]?.focus();
  }

  function toggleSeat(seatId: string) {
    if (hold) return;
    setSelected((current) => {
      if (current.includes(seatId)) return current.filter((id) => id !== seatId);
      if (current.length >= passengerCount) return current;
      return [...current, seatId];
    });
  }

  function updatePassenger(index: number, patch: Partial<PassengerDraft>) {
    setPassengers((current) => current.map((passenger, itemIndex) => (
      itemIndex === index ? { ...passenger, ...patch } : passenger
    )));
  }

  async function releaseHold() {
    if (!hold) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        browserApiUrl(`/v1/public/seat-holds/${encodeURIComponent(hold.hold_token)}/release`),
        { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() } },
      );
      if (!response.ok) {
        setError("تعذر تحرير المقاعد؛ ستتحرر تلقائيًا عند انتهاء المهلة.");
        return;
      }
      setHold(null);
      setSelected([]);
      sessionStorage.removeItem(storageKey);
      setAcceptedPolicies(false);
      holdKey.current = crypto.randomUUID();
      bookingKey.current = crypto.randomUUID();
    } catch {
      setError("تعذر الاتصال بالخادم؛ ستتحرر المقاعد تلقائيًا عند انتهاء المهلة.");
    } finally {
      setLoading(false);
    }
  }

  async function createHold() {
    setError(null);
    if (selected.length !== passengerCount) {
      setError(`اختر ${passengerCount} مقعدًا قبل المتابعة.`);
      return;
    }
    if (passengers.some((passenger) => passenger.fullName.trim().length < 2)) {
      setError("أدخل اسم كل مسافر لربطه بالمقعد المختار.");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(browserApiUrl(`/v1/public/trips/${trip.id}/seat-holds`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": holdKey.current,
        },
        body: JSON.stringify({
          seat_ids: selected,
          passengers: passengers.map((passenger, index) => ({
            full_name: passenger.fullName.trim(),
            gender: passenger.gender,
            passenger_type: passenger.passengerType,
            seat_id: selected[index],
          })),
          quote_version: trip.quote_version,
        }),
      });
      const payload = await response.json() as HoldResponse | { error?: { message?: string } };
      if (!response.ok || !("hold_token" in payload)) {
        setError("error" in payload ? payload.error?.message ?? "تعذر حفظ المقاعد." : "تعذر حفظ المقاعد.");
        return;
      }
      setHold(payload);
    } catch {
      setError("تعذر الاتصال بالخادم. لم تُحجز أي مقاعد.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmBooking() {
    if (!hold) return;
    setError(null);
    if (contactName.trim().length < 2 || contactPhone.trim().length < 8) {
      setError("أدخل اسم جهة الاتصال ورقم هاتف صالحًا.");
      return;
    }
    if (!acceptedPolicies) {
      setError("يجب قبول إصدارات السياسات المعروضة قبل إنشاء الحجز.");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(browserApiUrl("/v1/public/bookings"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": bookingKey.current,
        },
        body: JSON.stringify({
          trip_id: trip.id,
          hold_token: hold.hold_token,
          contact: {
            name: contactName.trim(),
            phone: contactPhone.trim(),
            email: contactEmail.trim() || null,
          },
          passengers: passengers.map((passenger, index) => ({
            full_name: passenger.fullName.trim(),
            gender: passenger.gender,
            passenger_type: passenger.passengerType,
            seat_id: selected[index],
          })),
          payment_method: paymentMethod,
          accepted_policy_version_ids: hold.quote.policy_version_ids,
          client_reference: `web-${bookingKey.current}`,
        }),
      });
      const payload = await response.json() as BookingResponse | { error?: { message?: string } };
      if (!response.ok || !("pnr" in payload)) {
        setError("error" in payload ? payload.error?.message ?? "تعذر إنشاء الحجز." : "تعذر إنشاء الحجز.");
        return;
      }
      setBooking(payload);
      sessionStorage.removeItem(storageKey);
    } catch {
      setError("تعذر الاتصال بالخادم. أعد المحاولة بالمفتاح نفسه؛ لن يتكرر الحجز.");
    } finally {
      setLoading(false);
    }
  }

  if (booking) {
    return (
      <section className="workspace-panel booking-success" aria-live="polite">
        <p className="eyebrow">تم إنشاء الحجز بنجاح</p>
        <h2>مرجع الحجز <bdi dir="ltr">{booking.pnr}</bdi></h2>
        <div className="success-grid">
          <div><span>حالة الحجز</span><strong>{booking.status}</strong></div>
          <div><span>حالة الدفع</span><strong>{booking.payment_status}</strong></div>
          <div><span>الإجمالي</span><strong><bdi dir="ltr">{formatMoney(booking.pricing.total.amount, booking.pricing.total.currency)}</bdi></strong></div>
          <div><span>المقاعد</span><strong>{booking.passengers.map((item) => item.seat_code).join("، ")}</strong></div>
        </div>
        {booking.payment_deadline_at ? (
          <p>مهلة الدفع حتى {new Intl.DateTimeFormat("ar-SY", { dateStyle: "medium", timeStyle: "short" }).format(new Date(booking.payment_deadline_at))}</p>
        ) : (
          <p>يمكن دفع قيمة الحجز في المكتب وفق الطريقة المختارة.</p>
        )}
        <div className="ticket-list">
          {booking.passengers.map((passenger) => (
            <article className="ticket-card" key={passenger.id}>
              <div>
                <small>المسافر</small>
                <strong>{passenger.full_name}</strong>
                <span>المقعد {passenger.seat_code}</span>
              </div>
              {passenger.ticket ? (
                <a
                  className="primary-link"
                  target="_blank"
                  rel="noreferrer"
                  href={browserApiUrl(`${passenger.ticket.pdf_url}?manage_token=${encodeURIComponent(booking.manage_token)}`)}
                >
                  عرض وطباعة التذكرة
                </a>
              ) : <span className="state-badge state-pending">تُصدر بعد تأكيد الدفع</span>}
            </article>
          ))}
        </div>
        <p className="form-note">احتفظ بالـPNR ورمز الإدارة. يمكنك استرجاع الحجز لاحقًا من صفحة متابعة الحجز.</p>
        <div className="action-row">
          <button type="button" onClick={() => navigator.clipboard.writeText(booking.pnr)}>نسخ PNR</button>
          <a className="text-link" href={`/manage-booking?pnr=${encodeURIComponent(booking.pnr)}`}>إدارة الحجز</a>
        </div>
      </section>
    );
  }

  return (
    <section className="seat-workspace" aria-busy={loading}>
      <article className="workspace-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">مخطط الإصدار {initialSeatMap.layout_version}</p>
            <h2>اختر {passengerCount} مقعدًا</h2>
          </div>
          <span className="state-badge state-active">{selected.length}/{passengerCount}</span>
        </div>
        <div className="seat-grid" aria-label="خريطة المقاعد">
          {initialSeatMap.seats.map((seat, index) => {
            const chosen = selected.includes(seat.id);
            const unavailable = seat.status !== "available" || Boolean(hold);
            return (
              <button
                className={`seat-button seat-${seat.status} ${chosen ? "seat-selected" : ""}`}
                type="button"
                key={seat.id}
                data-seat-index={index}
                tabIndex={index === 0 ? 0 : -1}
                aria-disabled={unavailable}
                aria-pressed={chosen}
                aria-label={`المقعد ${seat.code}، ${seatStatusLabels[seat.status] ?? seat.status}، ${seatTypeLabels[seat.type] ?? seat.type}${seat.price ? `، ${formatMoney(seat.price, trip.currency)}` : ""}`}
                onKeyDown={(event) => handleSeatKeyDown(event, index)}
                onClick={() => { if (!unavailable) toggleSeat(seat.id); }}
                title={`المقعد ${seat.code} · ${seatStatusLabels[seat.status] ?? seat.status}`}
              >
                <strong>{seat.code}</strong>
                <small>{seat.price ? <bdi dir="ltr">{formatMoney(seat.price, trip.currency)}</bdi> : seatStatusLabels[seat.status]}</small>
              </button>
            );
          })}
        </div>
        <div className="seat-legend">
          <span><i className="legend-available" /> متاح</span>
          <span><i className="legend-selected" /> محدد</span>
          <span><i className="legend-unavailable" /> غير متاح</span>
          <span><i className="legend-blocked" /> محجوب</span>
        </div>
      </article>

      <aside className="workspace-panel compact-panel passenger-panel">
        <p className="eyebrow">ربط المسافرين بالمقاعد</p>
        {passengers.map((passenger, index) => (
          <div className="passenger-card" key={`passenger-${index + 1}`}>
            <strong>المسافر {index + 1} · {selectedSeats[index]?.code ?? "دون مقعد"}</strong>
            <label>الاسم الكامل
              <input type="text" value={passenger.fullName} autoComplete="name" disabled={Boolean(hold)}
                onChange={(event) => updatePassenger(index, { fullName: event.target.value })} />
            </label>
            <select
              aria-label={`جنس المسافر ${index + 1}`}
              value={passenger.gender}
              disabled={Boolean(hold)}
              onChange={(event) => updatePassenger(index, { gender: event.target.value as "male" | "female" })}
            >
              <option value="male">ذكر</option>
              <option value="female">أنثى</option>
            </select>
            <select
              aria-label={`نوع المسافر ${index + 1}`}
              value={passenger.passengerType}
              disabled={Boolean(hold)}
              onChange={(event) => updatePassenger(index, {
                passengerType: event.target.value as PassengerDraft["passengerType"],
              })}
            >
              <option value="adult">بالغ</option>
              <option value="child">طفل</option>
              <option value="infant">رضيع</option>
            </select>
          </div>
        ))}
        {error ? <div className="operation-error" role="alert" tabIndex={-1} ref={errorRef}><p>{error}</p><button type="button" onClick={() => location.reload()}>إعادة المحاولة</button></div> : null}
        {hold ? (
          <div className="hold-success" role="status">
            <strong>تم حفظ المقاعد مؤقتًا</strong>
            <span>حتى <bdi dir="ltr">{formatTime(hold.expires_at)}</bdi></span>
            <span>الإجمالي: <bdi dir="ltr">{formatMoney(hold.quote.total.amount, hold.quote.total.currency)}</bdi></span>
            <label>اسم جهة الاتصال
              <input type="text" value={contactName} autoComplete="name" onChange={(event) => setContactName(event.target.value)} />
            </label>
            <label>رقم الهاتف
              <input type="tel" value={contactPhone} autoComplete="tel" dir="ltr" onChange={(event) => setContactPhone(event.target.value)} />
            </label>
            <label>البريد الإلكتروني — اختياري
              <input type="email" value={contactEmail} autoComplete="email" dir="ltr" onChange={(event) => setContactEmail(event.target.value)} />
            </label>
            <select aria-label="طريقة الدفع" value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}>
              {trip.payment_methods.map((method) => (
                <option value={method} key={method}>{paymentLabels[method] ?? method}</option>
              ))}
            </select>
            <section className="policy-summary-list" aria-labelledby="policy-summary-title">
              <h3 id="policy-summary-title">ملخص السياسات قبل التأكيد</h3>
              {trip.policy_summaries.map((policy) => (
                <article className="policy-summary-card" key={policy.id}>
                  <div><strong>{policy.title}</strong><small>الإصدار {policy.version_no} · {policy.language}</small></div>
                  <p>{policy.summary}</p>
                  <Link prefetch={false} href={`/policies/${encodeURIComponent(policy.code)}?office_id=${encodeURIComponent(trip.office.id)}`}>قراءة النص الكامل</Link>
                </article>
              ))}
            </section>
            <label className="policy-check">
              <input
                type="checkbox"
                checked={acceptedPolicies}
                onChange={(event) => setAcceptedPolicies(event.target.checked)}
              />
              أوافق على إصدارات سياسات الحجز والدفع والإلغاء المعروضة لهذه الرحلة.
            </label>
            <button type="button" disabled={loading} onClick={confirmBooking}>
              {loading ? "جارٍ تثبيت الحجز…" : "إنشاء الحجز النهائي"}
            </button>
            <button type="button" disabled={loading} onClick={releaseHold}>تحرير المقاعد</button>
          </div>
        ) : (
          <button type="button" disabled={loading} onClick={createHold}>
            {loading ? "جارٍ إعادة فحص المقاعد…" : "حفظ المقاعد مؤقتًا"}
          </button>
        )}
        <p className="form-note">الاختيار الظاهر ليس ضمانًا؛ الخادم يقفل المقاعد ويعيد فحصها عند التأكيد.</p>
      </aside>
    </section>
  );
}
