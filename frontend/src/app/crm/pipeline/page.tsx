import Link from "next/link";
import type { Metadata } from "next";
import { Handshake } from "lucide-react";
import { getPipelineBoard } from "@/lib/api/crm";
import { StageSelect } from "@/components/crm/stage-select";
import { TierBadge } from "@/components/badges/tier-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { formatScore } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Pipeline" };

export default async function PipelinePage() {
  const board = await getPipelineBoard();
  const total = board.columns.reduce((sum, col) => sum + col.opportunities.length, 0);
  const allStages = board.columns.map((c) => c.stage);

  if (total === 0) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="font-heading text-xl font-semibold text-foreground">Pipeline</h1>
        <EmptyState
          icon={<Handshake className="size-8" />}
          title="Nenhuma oportunidade no pipeline ainda."
          description="Crie uma oportunidade a partir de um prospect para vê-la aqui."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-xl font-semibold text-foreground">Pipeline</h1>
        <p className="text-sm text-muted-foreground">Use o seletor de etapa em cada card para mover a oportunidade.</p>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-2">
        {board.columns.map((column) => (
          <div key={column.stage.id} className="flex w-72 shrink-0 flex-col gap-3 rounded-lg bg-muted/40 p-3">
            <div className="flex items-center justify-between px-1">
              <h2 className="text-sm font-semibold text-foreground">{column.stage.name}</h2>
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {column.opportunities.length}
              </span>
            </div>

            <div className="flex flex-col gap-2">
              {column.opportunities.map((opp) => (
                <div key={opp.id} className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3">
                  <Link
                    href={`/crm/opportunities/${opp.id}`}
                    className="text-sm font-medium text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                  >
                    {opp.company_name}
                  </Link>
                  <div className="flex items-center justify-between">
                    <TierBadge tier={opp.opportunity_tier} />
                    <span className="font-mono text-xs font-medium tabular-nums text-muted-foreground">
                      {formatScore(opp.opportunity_score)}
                    </span>
                  </div>
                  {opp.status === "open" ? (
                    <StageSelect opportunityId={opp.id} stages={allStages} currentStageKey={column.stage.key} />
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
