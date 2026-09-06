import { CheckCircle2, AlertTriangle } from "lucide-react";
import { SectionCard } from "@/components/shared/section-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfidenceBadge } from "@/components/badges/confidence-badge";
import { evidenceFieldLabel, formatDateTime, EVIDENCE_STATE_HEDGE, SITE_STATE_LABEL } from "@/lib/format";
import type { EvidenceItem } from "@/lib/api/types";

export function EvidenceSection({ evidence }: { evidence: EvidenceItem[] }) {
  return (
    <SectionCard
      title="Evidências"
      description="Cada dado tem proveniência: nunca uma inferência apresentada como fato confirmado."
    >
      {evidence.length === 0 ? (
        <EmptyState title="Nenhuma evidência coletada ainda." className="py-8" />
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {evidence.map((item) => {
            const confirmed = item.state === "confirmed";
            const hedge = EVIDENCE_STATE_HEDGE[item.state];
            return (
              <li key={item.id} className="flex flex-col gap-1.5 rounded-lg border border-border p-3">
                <div className="flex items-center gap-1.5">
                  {confirmed ? (
                    <CheckCircle2 aria-hidden className="size-4 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <AlertTriangle aria-hidden className="size-4 text-amber-600 dark:text-amber-400" />
                  )}
                  <span className="text-sm font-medium text-foreground">{evidenceFieldLabel(item.field)}</span>
                  <span className="text-xs text-muted-foreground">
                    {confirmed ? "confirmado" : SITE_STATE_LABEL[item.state].toLowerCase()}
                  </span>
                </div>

                {item.value ? (
                  <p className="break-words text-sm text-foreground">{item.value}</p>
                ) : null}

                {hedge ? <p className="text-xs text-muted-foreground">{hedge}</p> : null}

                <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-muted-foreground">
                  <span>
                    Fonte: {item.source} · Coletado em {formatDateTime(item.collected_at)}
                  </span>
                  <ConfidenceBadge confidence={item.confidence} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}
