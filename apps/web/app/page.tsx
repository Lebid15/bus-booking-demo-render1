import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { getPublicLocations } from "@/lib/public-api";

export default async function PublicHomePage() {
  const locations = await getPublicLocations();
  const today = new Date().toISOString().slice(0, 10);

  return (
    <AppShell title="احجز مقعدك بين المدن بسهولة" eyebrow="الموقع العام">
      <section className="hero-grid">
        <div className="hero-copy">
          <h2>رحلتك تبدأ من اختيار واضح ومقعد مؤكد</h2>
          <p>
            ابحث حسب نقطة الانطلاق والوصول والتاريخ، ثم اختر الرحلة والمقعد وأكمل بيانات المسافرين.
          </p>
          <div className="trust-row" aria-label="ميزات الحجز">
            <span>مقاعد حية</span>
            <span>سعر معلن مع الرسوم</span>
            <span>إعادة تحقق عند الاختيار</span>
          </div>
        </div>
        <form className="search-card" action="/search" method="get" aria-label="البحث عن رحلة">
          <label>
            من
            <select name="origin_id" required defaultValue="">
              <option value="" disabled>اختر نقطة الانطلاق</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>{location.name}</option>
              ))}
            </select>
          </label>
          <label>
            إلى
            <select name="destination_id" required defaultValue="">
              <option value="" disabled>اختر نقطة الوصول</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>{location.name}</option>
              ))}
            </select>
          </label>
          <label>
            تاريخ الرحلة
            <input type="date" name="date" min={today} defaultValue={today} required />
          </label>
          <label>
            عدد المسافرين
            <input type="number" name="passengers" min="1" max="8" defaultValue="1" required />
          </label>
          <button type="submit">البحث عن الرحلات</button>
          <p className="form-note">
            {locations.length > 0
              ? "تظهر فقط الرحلات المفتوحة للحجز والمكاتب المسموح لها باستقبال حجوزات جديدة."
              : "تعذر تحميل نقاط السفر حاليًا؛ شغّل API ثم أعد المحاولة."}
          </p>
        </form>
      </section>
      <section className="feature-grid" aria-label="روابط الخدمة">
        <article className="feature-card">
          <span className="feature-number">01</span>
          <h3>متابعة حجز</h3>
          <p>عرض حالة الحجز وإكمال الدفع وتنزيل التذكرة باستخدام رمز الإدارة الآمن.</p>
          <Link href="/manage-booking">استرجاع الحجز والتذكرة</Link>
        </article>
        <article className="feature-card">
          <span className="feature-number">02</span>
          <h3>حجز دون حساب</h3>
          <p>الحساب اختياري، ويمكن تثبيت المقاعد مؤقتًا قبل إنشاء الحجز النهائي.</p>
        </article>
        <article className="feature-card">
          <span className="feature-number">03</span>
          <h3>مخزون موحد</h3>
          <p>الخادم يعيد فحص المقعد عند الحفظ، ولا يعتمد لون المقعد الذي ظهر سابقًا.</p>
        </article>
      </section>
    </AppShell>
  );
}
