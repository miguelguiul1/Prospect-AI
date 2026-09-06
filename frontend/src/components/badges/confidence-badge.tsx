import { ShieldCheck, ShieldQuestion, ShieldHalf } from "lucide-react";
import { cn } from "@/lib/utils";
import { CONFIDENCE_LABEL } from "@/lib/format";
import type { ConfidenceLevel } from "@/lib/api/types";

const ICON: Record<ConfidenceLevel, typeof ShieldCheck> = {
  high: ShieldCheck,
  medium: ShieldHalf,
  low: ShieldQuestion,
};

/** Nunca usa cor como único indicador — o ícone e o texto mudam junto,
 * para permanecer legível também para quem não distingue cor (WCAG). */
export function ConfidenceBadge({
  confidence,
  className,
}: {
  confidence: ConfidenceLevel | null;
  className?: string;
}) {
  if (!confidence) {
    return (
      <span className={cn("inline-flex items-center gap-1 text-xs text-muted-foreground", className)}>
        —
      </span>
    );
  }

  const Icon = ICON[confidence];
  return (
    <span
      className={cn("inline-flex items-center gap-1 text-xs text-muted-foreground", className)}
      data-testid="confidence-badge"
      title={`Confiança ${CONFIDENCE_LABEL[confidence]}`}
    >
      <Icon aria-hidden className="size-3.5" />
      {CONFIDENCE_LABEL[confidence]}
    </span>
  );
}
