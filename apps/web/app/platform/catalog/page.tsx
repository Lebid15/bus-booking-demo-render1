import Link from "next/link";

import { AppShell } from "@/components/app-shell";

const catalogRows = [
  ["الرقة", "مدينة", "نشط"],
  ["كراج البولمن · الرقة", "كراج", "نشط"],
  ["دمشق", "مدينة", "نشط"],
  ["الرقة ← دمشق", "مسار اتجاهي", "نشط"],
];

export default function PlatformCatalogPage() {
  return (
    <AppShell title="الجغرافيا والمسارات" eyebrow="إدارة المنصة · الكتالوج">
      <section className="workspace-panel table-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">كتالوج مركزي</p>
            <h2>المواقع والخطوط التشغيلية</h2>
          </div>
          <button type="button">إضافة موقع</button>
        </div>
        <div className="data-table" role="table" aria-label="كتالوج المواقع والمسارات">
          {catalogRows.map(([name, type, state]) => (
            <div className="data-row" role="row" key={`${name}-${type}`}>
              <strong role="cell">{name}</strong>
              <span role="cell">{type}</span>
              <span className="state-badge state-active" role="cell">{state}</span>
            </div>
          ))}
        </div>
        <p className="form-note">
          خط الرقة إلى دمشق لا ينشئ خط دمشق إلى الرقة تلقائيًا؛ كل اتجاه سجل مستقل.
        </p>
        <Link className="text-link" href="/platform">العودة إلى مركز التحكم</Link>
      </section>
    </AppShell>
  );
}
