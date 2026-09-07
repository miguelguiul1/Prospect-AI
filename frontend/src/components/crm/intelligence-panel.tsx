import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { TierBadge } from "@/components/badges/tier-badge";
import { ConfidenceBadge } from "@/components/badges/confidence-badge";
import { SiteStateBadge } from "@/components/badges/site-state-badge";
import { formatScore } from "@/lib/format";
import type { OpportunityDetail } from "@/lib/api/types";

/** "Por que esta oportunidade está aqui?" — Opportunity Score, Website
 * Quality e Sales Brief consolidados numa única leitura (Prompt 11, seção
 * 13). Nenhum valor é recalculado aqui — tudo já vem pronto do backend
 * (F3/F4), só composto visualmente. */
export function IntelligencePanel({ opportunity }: { opportunity: OpportunityDetail }) {
  const brief = opportunity.sales_brief_content;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <p className="text-xs text-muted-foreground">Opportunity Score</p>
          <p className="font-mono text-lg font-semibold tabular-nums text-foreground">
            {formatScore(opportunity.opportunity_score)}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Classificação</p>
          <TierBadge tier={opportunity.opportunity_tier} className="mt-1" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Confiança</p>
          <ConfidenceBadge confidence={opportunity.opportunity_confidence} className="mt-1" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Qualidade do site</p>
          <p className="font-mono text-lg font-semibold tabular-nums text-foreground">
            {formatScore(opportunity.website_quality_score)}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SiteStateBadge state={opportunity.site_state} />
        {opportunity.website_url ? (
          <a
            href={opportunity.website_url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            {opportunity.website_url}
            <ExternalLink className="size-3" />
          </a>
        ) : null}
      </div>

      {opportunity.sales_brief_status === "completed" && brief ? (
        <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
          <p className="text-sm text-foreground">{brief.summary}</p>
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Ângulo sugerido: </span>
            {brief.suggested_angle}
          </p>
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Gaps digitais: </span>
            {brief.digital_gaps}
          </p>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Nenhum Sales Brief disponível ainda.{" "}
          <Link href={`/prospects/${opportunity.company_id}`} className="text-primary hover:underline">
            Gerar no detalhe do prospect
          </Link>
          .
        </p>
      )}
    </div>
  );
}
