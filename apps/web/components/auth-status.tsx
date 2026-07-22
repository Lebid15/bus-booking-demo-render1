"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { clearAuthSession, useAuthSession } from "@/lib/auth";

export function AuthStatus() {
  const router = useRouter();
  const session = useAuthSession();
  if (!session) return <Link href="/login" className="auth-link">تسجيل الدخول</Link>;
  return (
    <div className="auth-status">
      <span>{session.user.full_name}</span>
      <button
        type="button"
        onClick={() => {
          clearAuthSession();
          router.push("/login");
          router.refresh();
        }}
      >
        خروج
      </button>
    </div>
  );
}
