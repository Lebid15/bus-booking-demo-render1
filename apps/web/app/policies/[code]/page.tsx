import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { getPublicPolicy } from "@/lib/public-api";

type PolicyPageProps = { params: Promise<{ code: string }>; searchParams: Promise<{ office_id?: string }> };

export default async function PolicyPage({ params, searchParams }: PolicyPageProps) {
  const { code } = await params;
  const { office_id: officeId } = await searchParams;
  const policy = await getPublicPolicy(code, officeId);
  if (!policy) notFound();
  return <AppShell title={policy.title} eyebrow={`السياسات · ${policy.code} · الإصدار ${policy.version_no}`}>
    <section className="status-banner status-success"><strong>إصدار نافذ وقابل للتحقق</strong><span>اللغة: {policy.language} · تاريخ النفاذ: {policy.effective_from}</span></section>
    <article className="workspace-panel"><pre className="policy-content">{policy.content_markdown}</pre><p className="form-note">SHA-256: {policy.content_sha256}</p></article>
  </AppShell>;
}
