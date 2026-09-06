import { Clock, Loader2, CheckCircle2, AlertTriangle, XCircle, Ban } from "lucide-react";
import { cn } from "@/lib/utils";
import { SEARCH_RUN_STATUS_LABEL, AUDIT_STATUS_LABEL } from "@/lib/format";
import type { SearchRunStatus, AuditStatus } from "@/lib/api/types";

const RUN_STYLE: Record<SearchRunStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  running: "bg-primary/10 text-primary",
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  partially_completed: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  failed: "bg-destructive/10 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
};

const RUN_ICON: Record<SearchRunStatus, typeof Clock> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle2,
  partially_completed: AlertTriangle,
  failed: XCircle,
  cancelled: Ban,
};

export function RunStatusBadge({ status, className }: { status: SearchRunStatus; className?: string }) {
  const Icon = RUN_ICON[status];
  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit items-center gap-1 rounded-full px-2 text-xs font-medium whitespace-nowrap",
        RUN_STYLE[status],
        className
      )}
      data-testid="run-status-badge"
    >
      <Icon aria-hidden className={cn("size-3.5", status === "running" && "animate-spin")} />
      {SEARCH_RUN_STATUS_LABEL[status]}
    </span>
  );
}

const AUDIT_STYLE: Record<AuditStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  running: "bg-primary/10 text-primary",
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  failed: "bg-destructive/10 text-destructive",
};

const AUDIT_ICON: Record<AuditStatus, typeof Clock> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
};

export function AuditStatusBadge({ status, className }: { status: AuditStatus; className?: string }) {
  const Icon = AUDIT_ICON[status];
  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit items-center gap-1 rounded-full px-2 text-xs font-medium whitespace-nowrap",
        AUDIT_STYLE[status],
        className
      )}
      data-testid="audit-status-badge"
    >
      <Icon aria-hidden className={cn("size-3.5", status === "running" && "animate-spin")} />
      {AUDIT_STATUS_LABEL[status]}
    </span>
  );
}
