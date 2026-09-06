import { cn } from "@/lib/utils";
import { TIER_LABEL } from "@/lib/format";
import type { OpportunityTier } from "@/lib/api/types";

const TIER_STYLES: Record<OpportunityTier, string> = {
  high: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  medium_high: "bg-teal-100 text-teal-800 dark:bg-teal-500/15 dark:text-teal-300",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  low: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
  very_low: "bg-muted text-muted-foreground",
};

export function TierBadge({
  tier,
  className,
}: {
  tier: OpportunityTier | null;
  className?: string;
}) {
  if (!tier) {
    return (
      <span
        className={cn(
          "inline-flex h-5 w-fit items-center rounded-full border border-border px-2 text-xs font-medium text-muted-foreground",
          className
        )}
      >
        Sem score
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit items-center rounded-full px-2 text-xs font-medium whitespace-nowrap",
        TIER_STYLES[tier],
        className
      )}
      data-testid="tier-badge"
    >
      {TIER_LABEL[tier]}
    </span>
  );
}
