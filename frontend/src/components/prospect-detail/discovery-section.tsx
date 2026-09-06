import { SectionCard } from "@/components/shared/section-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfidenceBadge } from "@/components/badges/confidence-badge";
import { formatDateTime } from "@/lib/format";
import type { CompanySource } from "@/lib/api/types";

export function DiscoverySection({ sources }: { sources: CompanySource[] }) {
  return (
    <SectionCard
      title="Descoberta"
      description="Fontes externas que reportaram esta empresa (Fase 1/2)."
    >
      {sources.length === 0 ? (
        <EmptyState title="Nenhuma fonte registrada." className="py-8" />
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {sources.map((source) => (
            <li key={source.id} className="flex flex-wrap items-center justify-between gap-2 py-3 first:pt-0 last:pb-0">
              <div>
                <p className="text-sm font-medium text-foreground">{source.source}</p>
                <p className="text-xs text-muted-foreground">ID externo: {source.external_id}</p>
                <p className="text-xs text-muted-foreground">
                  Visto pela primeira vez em {formatDateTime(source.first_seen_at)} · última vez em{" "}
                  {formatDateTime(source.last_seen_at)}
                </p>
              </div>
              <ConfidenceBadge confidence={source.confidence} />
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
