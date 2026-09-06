import { SectionCard } from "@/components/shared/section-card";
import { SiteStateBadge } from "@/components/badges/site-state-badge";
import { SITE_STATE_DESCRIPTION, formatDateTime } from "@/lib/format";
import type { AuditSnapshotDetail } from "@/lib/api/types";

function signalString(signals: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = signals?.[key];
  if (value === null || value === undefined) return null;
  return String(value);
}

export function WebsiteSection({ audit }: { audit: AuditSnapshotDetail | null }) {
  if (!audit) {
    return (
      <SectionCard title="Website" description="Nenhuma auditoria digital foi executada ainda.">
        <p className="text-sm text-muted-foreground">
          Rode uma auditoria para verificar se esta empresa tem um website próprio acessível.
        </p>
      </SectionCard>
    );
  }

  const signals = audit.website_quality?.signals ?? null;
  const httpsValue = signalString(signals, "https");
  const statusCode = signalString(signals, "status_code");
  const responseTime = signalString(signals, "response_time_ms");
  const redirects = signalString(signals, "redirect_count");

  const rows: { label: string; value: string }[] = [
    { label: "URL auditada", value: audit.website_url ?? "Nenhuma" },
    { label: "HTTPS", value: httpsValue === "true" ? "Sim" : httpsValue === "false" ? "Não" : "—" },
    { label: "Status HTTP", value: statusCode ?? "—" },
    { label: "Tempo de resposta", value: responseTime ? `${responseTime} ms` : "—" },
    { label: "Redirecionamentos", value: redirects ?? "—" },
    { label: "Auditado em", value: formatDateTime(audit.created_at) },
  ];

  return (
    <SectionCard title="Website" action={<SiteStateBadge state={audit.site_state} />}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          {audit.site_state ? SITE_STATE_DESCRIPTION[audit.site_state] : null}
        </p>
        {audit.error_message ? (
          <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">{audit.error_message}</p>
        ) : null}
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          {rows.map((row) => (
            <div key={row.label} className="flex flex-col gap-0.5">
              <dt className="text-xs font-medium text-muted-foreground">{row.label}</dt>
              <dd className="text-sm break-all text-foreground">{row.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </SectionCard>
  );
}
