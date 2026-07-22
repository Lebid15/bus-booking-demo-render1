"use client";
export default function SeatsError({ reset }: { reset: () => void }) {
  return <section className="operation-error" role="alert"><h2>تعذر تحميل المقاعد</h2><p>لم يُحجز أي مقعد. أعد المحاولة عند استقرار الاتصال.</p><button type="button" onClick={reset}>إعادة تحميل الخريطة</button></section>;
}
