import { SectionCard } from "@/components/shared/section-card";
import { ActionButton } from "@/components/prospect-detail/action-button";
import { generateBriefAction } from "@/app/prospects/[companyId]/actions";
import { formatDateTime } from "@/lib/format";
import { Sparkles } from "lucide-react";
import type { SalesBriefDetail } from "@/lib/api/types";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</h4>
      <p className="text-sm text-foreground">{value}</p>
    </div>
  );
}

export function SalesBriefSection({
  companyId,
  brief,
  hasScore,
}: {
  companyId: string;
  brief: SalesBriefDetail | null;
  hasScore: boolean;
}) {
  const generateButton = (
    <ActionButton
      action={generateBriefAction}
      companyId={companyId}
      label={brief ? "Gerar novamente" : "Gerar Sales Brief"}
      pendingLabel="Gerando…"
      icon={<Sparkles className="size-4" />}
    />
  );

  if (!hasScore) {
    return (
      <SectionCard title="Sales Brief">
        <p className="text-sm text-muted-foreground">
          Calcule o Opportunity Score antes de gerar o Sales Brief.
        </p>
      </SectionCard>
    );
  }

  if (!brief) {
    return (
      <SectionCard title="Sales Brief">
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-muted-foreground">Sales Brief ainda não gerado.</p>
          {generateButton}
        </div>
      </SectionCard>
    );
  }

  if (brief.status === "failed") {
    return (
      <SectionCard title="Sales Brief" description={`Última tentativa em ${formatDateTime(brief.generated_at)}`}>
        <div className="flex flex-col items-start gap-3">
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {brief.error_message ?? "O provider de IA não conseguiu gerar o briefing."}
          </p>
          {generateButton}
        </div>
      </SectionCard>
    );
  }

  const content = brief.content;
  if (!content) return null;

  return (
    <SectionCard
      title="Sales Brief"
      description={`Gerado em ${formatDateTime(brief.generated_at)} · ${brief.provider ?? "provider"}${brief.model ? ` (${brief.model})` : ""}`}
      action={generateButton}
    >
      <div className="flex flex-col gap-4">
        <Field label="Resumo" value={content.summary} />
        <Field label="Oportunidade" value={content.opportunity} />
        <Field label="Por que este prospect" value={content.why_this_prospect} />
        <Field label="Gaps digitais" value={content.digital_gaps} />
        <Field label="Abordagem sugerida" value={content.suggested_angle} />

        <div className="space-y-1">
          <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Talking points
          </h4>
          <ul className="list-inside list-disc space-y-1 text-sm text-foreground">
            {content.talking_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </div>

        <Field label="Riscos e ressalvas" value={content.risks_and_caveats} />

        <div className="space-y-1">
          <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Evidências usadas
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {content.evidence_used.map((item, i) => (
              <span key={i} className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-xs text-muted-foreground">
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
