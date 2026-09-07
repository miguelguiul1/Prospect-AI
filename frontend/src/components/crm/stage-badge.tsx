import { cn } from "@/lib/utils";
import type { PipelineStage } from "@/lib/api/types";

export function StageBadge({ stage, className }: { stage: PipelineStage; className?: string }) {
  const style = stage.is_won
    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300"
    : stage.is_lost
      ? "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300"
      : "bg-accent text-accent-foreground";

  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit items-center rounded-full px-2 text-xs font-medium whitespace-nowrap",
        style,
        className
      )}
    >
      {stage.name}
    </span>
  );
}
