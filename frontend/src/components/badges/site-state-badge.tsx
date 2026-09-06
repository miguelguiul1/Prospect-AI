import {
  CheckCircle2,
  CircleDashed,
  HelpCircle,
  AlertTriangle,
  Clock,
  History,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SITE_STATE_LABEL } from "@/lib/format";
import type { DataState } from "@/lib/api/types";

const STYLE: Record<DataState, string> = {
  confirmed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  not_detected: "bg-muted text-muted-foreground",
  inconclusive: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  inaccessible: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
  not_checked: "bg-muted text-muted-foreground",
  stale: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
};

const ICON: Record<DataState, typeof CheckCircle2> = {
  confirmed: CheckCircle2,
  not_detected: CircleDashed,
  inconclusive: HelpCircle,
  inaccessible: AlertTriangle,
  not_checked: Clock,
  stale: History,
};

/** Nunca colapsa `not_detected` em "sem website" definitivo — o rótulo
 * exato do `DataState` (Fase 0) é sempre preservado, nunca reinterpretado. */
export function SiteStateBadge({
  state,
  className,
}: {
  state: DataState | null;
  className?: string;
}) {
  if (!state) {
    return (
      <span className={cn("inline-flex h-5 w-fit items-center rounded-full border border-border px-2 text-xs font-medium text-muted-foreground", className)}>
        Não auditado
      </span>
    );
  }

  const Icon = ICON[state];
  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit items-center gap-1 rounded-full px-2 text-xs font-medium whitespace-nowrap",
        STYLE[state],
        className
      )}
      data-testid="site-state-badge"
    >
      <Icon aria-hidden className="size-3.5" />
      {SITE_STATE_LABEL[state]}
    </span>
  );
}
