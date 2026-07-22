"use client";
export default function SearchError({ reset }: { reset: () => void }) {
  return <section className="operation-error" role="alert"><h2>تعذر تحميل الرحلات</h2><p>تحقق من الاتصال ثم أعد المحاولة. بقيت بيانات البحث في العنوان.</p><button type="button" onClick={reset}>إعادة المحاولة</button></section>;
}
