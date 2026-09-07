import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { StageBadge } from "@/components/crm/stage-badge";
import { TierBadge } from "@/components/badges/tier-badge";
import { formatScore } from "@/lib/format";
import type { OpportunitySummary } from "@/lib/api/types";

export function OpportunitiesList({ items }: { items: OpportunitySummary[] }) {
  return (
    <ul className="divide-y divide-border rounded-lg border border-border bg-card">
      {items.map((item) => (
        <li key={item.id}>
          <Link
            href={`/crm/opportunities/${item.id}`}
            className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-foreground">{item.company_name}</p>
              <p className="text-xs text-muted-foreground">
                {item.category_name ?? "Sem categoria"}
                {item.region_name ? ` · ${item.region_name}` : ""}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm font-medium tabular-nums text-foreground">
                {formatScore(item.opportunity_score)}
              </span>
              <TierBadge tier={item.opportunity_tier} />
              <StageBadge stage={item.stage} />
              <ChevronRight className="size-4 text-muted-foreground" />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
