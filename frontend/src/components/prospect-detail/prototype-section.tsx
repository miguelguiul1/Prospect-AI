import { SectionCard } from "@/components/shared/section-card";
import { ActionButton } from "@/components/prospect-detail/action-button";
import { generatePrototypeAction } from "@/app/prospects/[companyId]/actions";
import { LayoutTemplate } from "lucide-react";

/**
 * Fecha a lacuna identificada no relatório do Prompt 10: o ponto de
 * entrada real para gerar um protótipo com contexto de empresa (Fase 9 /
 * Prompt 11). Deliberadamente simples — a ação redireciona para o
 * Prototype Builder já populado ao terminar (`generatePrototypeAction`),
 * então esta seção nunca precisa mostrar um resultado inline como
 * `SalesBriefSection` mostra: ou o usuário ainda está aqui (nada gerado
 * ainda / geração em andamento), ou já foi redirecionado.
 */
export function PrototypeSection({ companyId, hasOpportunity }: { companyId: string; hasOpportunity: boolean }) {
  if (!hasOpportunity) {
    return (
      <SectionCard title="Protótipo">
        <p className="text-sm text-muted-foreground">
          Crie uma oportunidade para esta empresa antes de gerar um protótipo.
        </p>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title="Protótipo"
      description="Gera um protótipo de site por IA a partir dos dados reais desta empresa — evidências, auditoria digital e Sales Brief, quando existirem."
    >
      <ActionButton
        action={generatePrototypeAction}
        companyId={companyId}
        label="Gerar Protótipo"
        pendingLabel="Gerando…"
        icon={<LayoutTemplate className="size-4" />}
      />
    </SectionCard>
  );
}
