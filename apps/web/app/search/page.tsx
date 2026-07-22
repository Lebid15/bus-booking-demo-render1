import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import { getPublicLocations, searchTrips } from "@/lib/public-api";

type SearchPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}


export default async function SearchPage({ searchParams }: SearchPageProps) {
  const raw = await searchParams;
  const originId = first(raw.origin_id);
  const destinationId = first(raw.destination_id);
  const date = first(raw.date);
  const passengers = Math.min(8, Math.max(1, Number(first(raw.passengers)) || 1));
  const locations = await getPublicLocations();
  const searched = Boolean(originId && destinationId && date);
  const trips = searched
    ? await searchTrips({ originId, destinationId, date, passengers })
    : [];

  return (
    <AppShell title="نتائج الرحلات" eyebrow="البحث العام · توفر حي">
      <form id="search-form" className="search-card compact-search" action="/search" method="get">
        <label>
          من
          <select name="origin_id" required defaultValue={originId}>
            <option value="" disabled>اختر الانطلاق</option>
            {locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}
          </select>
        </label>
        <label>
          إلى
          <select name="destination_id" required defaultValue={destinationId}>
            <option value="" disabled>اختر الوصول</option>
            {locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}
          </select>
        </label>
        <label>
          التاريخ
          <input type="date" name="date" required defaultValue={date} />
        </label>
        <label>
          المسافرون
          <input type="number" name="passengers" min="1" max="8" defaultValue={passengers} />
        </label>
        <button type="submit">تحديث البحث</button>
      </form>

      <section className="trip-results" aria-live="polite">
        {!searched ? (
          <div className="empty-state"><h2>ابدأ بإدخال بيانات الرحلة</h2><p>حدد الانطلاق والوصول والتاريخ لعرض الرحلات.</p><a className="primary-link" href="#search-form">بدء البحث</a></div>
        ) : trips.length === 0 ? (
          <div className="empty-state">
            <h2>لا توجد رحلات قابلة للحجز</h2>
            <p>جرّب تاريخًا آخر أو غيّر نقاط الانطلاق والوصول.</p>
            <a className="primary-link" href="#search-form">تعديل البحث</a>
          </div>
        ) : trips.map((trip) => (
          <article className="trip-card" key={trip.id}>
            <div className="trip-time">
              <strong>{formatDateTime(trip.departure_at)}</strong>
              <span>{trip.arrival_at ? formatDateTime(trip.arrival_at) : "الوصول يحدد لاحقًا"}</span>
            </div>
            <div className="trip-route">
              <h2>{trip.origin.name} ← {trip.destination.name}</h2>
              <p>{trip.office.name} · {trip.operator.name}</p>
              <div className="trust-row">
                <span>{formatNumber(trip.available_seats)} مقعدًا متاحًا</span>
                {trip.payment_methods.map((method) => <span key={method}>{method}</span>)}
              </div>
              {trip.cancellation_summary ? <small>{trip.cancellation_summary}</small> : null}
            </div>
            <div className="trip-price">
              <small>السعر المعلن من</small>
              <strong><bdi dir="ltr">{formatMoney(trip.from_price, trip.currency)}</bdi></strong>
              <Link className="primary-link" href={`/trips/${trip.id}/seats?passengers=${passengers}`}>
                اختيار المقاعد
              </Link>
            </div>
          </article>
        ))}
      </section>
    </AppShell>
  );
}
