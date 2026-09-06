import { SectionCard } from "@/components/shared/section-card";
import { formatDateTime, formatScore } from "@/lib/format";
import type { AuditSnapshotDetail } from "@/lib/api/types";

const COMPONENT_LABEL: Record<string, string> = {
  security: "Segurança",
  seo: "SEO técnico",
  content: "Conteúdo",
  ux: "UX/Mobile",
  technical: "Aspectos técnicos",
};

export function WebsiteQualitySection({ audit }: { audit: AuditSnapshotDetail | null }) {
  const quality = audit?.website_quality;

  if (!quality || quality.score === null) {
    return (
      <SectionCard title="Website Quality Score">
        <p className="text-sm text-muted-foreground">
          {quality?.limitations?.[0] ??
            "Não avaliável: o site não foi confirmado como acessível nesta auditoria."}
        </p>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title="Website Quality Score"
      description={`Calculado em ${formatDateTime(audit?.created_at)}`}
    >
      <div className="flex flex-col gap-4">
        <p className="font-mono text-3xl font-semibold tabular-nums text-foreground">
          {formatScore(quality.score)}
          <span className="ml-1 text-base font-normal text-muted-foreground">/ 100</span>
        </p>

        {quality.components ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {Object.entries(quality.components).map(([key, value]) => (
              <div key={key} className="flex flex-col gap-1 rounded-md border border-border p-2.5">
                <span className="text-xs text-muted-foreground">{COMPONENT_LABEL[key] ?? key}</span>
                <span className="font-mono text-sm font-medium tabular-nums text-foreground">
                  {formatScore(value)}
                </span>
              </div>
            ))}
          </div>
        ) : null}

        {quality.limitations && quality.limitations.length > 0 ? (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Limitações</p>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {quality.limitations.map((limitation, i) => (
                <li key={i}>{limitation}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </SectionCard>
  );
}
