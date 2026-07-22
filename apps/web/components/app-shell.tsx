import Link from "next/link";
import type { ReactNode } from "react";

import { AuthStatus } from "@/components/auth-status";
import { HealthPill } from "@/components/health-pill";

type AppShellProps = {
  title: string;
  eyebrow: string;
  children: ReactNode;
};

export function AppShell({ title, eyebrow, children }: AppShellProps) {
  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">انتقل إلى المحتوى الرئيسي</a>
      <header className="topbar">
        <Link href="/" className="brand" aria-label="العودة إلى الموقع العام">
          <span className="brand-mark" aria-hidden="true">ب</span>
          <span>منصة حجز البولمن</span>
        </Link>
        <nav className="topnav" aria-label="التنقل الرئيسي">
          <Link href="/">الحجز العام</Link>
          <Link href="/office">لوحة المكتب</Link>
          <Link href="/platform">إدارة المنصة</Link>
          <Link href="/notifications">الإشعارات</Link>
          <Link href="/privacy">الخصوصية</Link>
        </nav>
        <div className="topbar-actions"><AuthStatus /><HealthPill /></div>
      </header>
      <main id="main-content" tabIndex={-1}>
      <section className="page-heading">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </section>
      {children}
      </main>
    </div>
  );
}
