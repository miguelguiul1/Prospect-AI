import { SectionCard } from "@/components/shared/section-card";
import { TierBadge } from "@/components/badges/tier-badge";
import { ConfidenceBadge } from "@/components/badges/confidence-badge";
import { formatDateTime, formatScore } from "@/lib/format";
import type { OpportunityScoreDetail } from "@/lib/api/types";

export function OpportunitySection({ score }: { score: OpportunityScoreDetail | null }) {
  if (!score) {
    return (
      <SectionCard title="Opportunity Score">
        <p className="text-sm text-muted-foreground">
          Ainda não calculado. É necessário rodar uma auditoria digital primeiro.
        </p>
      </SectionCard>
    );
  }

  return (
    <SectionCard title="Opportunity Score" action={<TierBadge tier={score.tier} />}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <p className="font-mono text-4xl font-semibold tabular-nums text-foreground">
          {formatScore(score.score)}
          <span className="ml-1 text-base font-normal text-muted-foreground">/ 100</span>
        </p>
        <dl className="grid grid-cols-3 gap-4 text-right">
          <div>
            <dt className="text-xs text-muted-foreground">Confiança</dt>
            <dd>
              <ConfidenceBadge confidence={score.confidence} className="justify-end" />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Versão</dt>
            <dd className="text-sm text-foreground">{score.scoring_version}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Calculado em</dt>
            <dd className="text-sm text-foreground">{formatDateTime(score.updated_at)}</dd>
          </div>
        </dl>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Heurística de priorização comercial — não é uma probabilidade de conversão nem uma
        estimativa de faturamento. Ver detalhamento por dimensão abaixo.
      </p>
    </SectionCard>
  );
}
