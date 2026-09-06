import { SectionCard } from "@/components/shared/section-card";
import { dimensionLabel } from "@/lib/format";
import type { OpportunityBreakdown } from "@/lib/api/types";

const DIMENSION_ORDER = [
  "website_gap",
  "website_quality_gap",
  "digital_presence_gap",
  "business_visibility",
  "segment_fit",
  "contactability",
];

export function BreakdownSection({ breakdown }: { breakdown: OpportunityBreakdown | null }) {
  if (!breakdown) {
    return (
      <SectionCard title="Como o score foi calculado">
        <p className="text-sm text-muted-foreground">Sem breakdown disponível — score ainda não calculado.</p>
      </SectionCard>
    );
  }

  const keys = DIMENSION_ORDER.filter((k) => k in breakdown.dimensions).concat(
    Object.keys(breakdown.dimensions).filter((k) => !DIMENSION_ORDER.includes(k))
  );

  return (
    <SectionCard
      title="Como o score foi calculado"
      description="Cada dimensão explica sua própria contribuição para o score final — nenhum número é uma caixa-preta."
    >
      <ul className="flex flex-col divide-y divide-border">
        {keys.map((key) => {
          const dim = breakdown.dimensions[key];
          const excluded = dim.raw === null;
          return (
            <li key={key} className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-medium text-foreground">{dimensionLabel(key)}</h3>
                <span className="text-xs text-muted-foreground">
                  peso {Math.round(dim.weight * 100)}%
                </span>
              </div>

              {excluded ? (
                <p className="text-sm text-muted-foreground italic">
                  Excluído do cálculo — evidência insuficiente para esta dimensão.
                </p>
              ) : (
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  <span className="font-mono tabular-nums text-foreground">
                    valor {dim.raw!.toFixed(1)}
                  </span>
                  <span className="font-mono tabular-nums text-muted-foreground">
                    contribuição {dim.contribution!.toFixed(1)}
                  </span>
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.min(100, Math.max(0, dim.raw!))}%` }}
                    />
                  </div>
                </div>
              )}

              <p className="text-sm text-muted-foreground">{dim.reason}</p>

              {dim.evidence_refs.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {dim.evidence_refs.map((ref, i) => (
                    <span
                      key={i}
                      className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-xs text-muted-foreground"
                    >
                      {ref.field}: {String(ref.value)}
                    </span>
                  ))}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </SectionCard>
  );
}
