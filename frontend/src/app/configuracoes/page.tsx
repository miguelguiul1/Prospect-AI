import type { Metadata } from "next";
import { SectionCard } from "@/components/shared/section-card";
import { Badge } from "@/components/ui/badge";

export const metadata: Metadata = { title: "Configurações" };

const IMPLEMENTED_PHASES = [
  "Fase 0 — Foundation",
  "Fase 1 — Discovery",
  "Fase 2 — Identity Resolution + Deduplicação",
  "Fase 3 — Digital Audit + Website Quality Score",
  "Fase 4 — Opportunity Score + Sales Brief",
  "Fase 5 — Dashboard",
];

export default function ConfiguracoesPage() {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-xl font-semibold text-foreground">Configurações</h1>
        <p className="text-sm text-muted-foreground">
          Não há preferências de usuário nesta fase — o sistema ainda não tem autenticação/multi-tenant.
          Esta tela mostra apenas informações reais do ambiente.
        </p>
      </div>

      <SectionCard title="Conexão com a API">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs font-medium text-muted-foreground">URL base do backend</dt>
            <dd className="font-mono text-sm text-foreground">{apiBaseUrl}</dd>
          </div>
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs font-medium text-muted-foreground">Provider de Discovery</dt>
            <dd className="text-sm text-foreground">Google Places (único implementado)</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-muted-foreground">
          Nenhuma API key (Google Maps, Anthropic) é lida ou exibida pelo frontend — elas ficam
          exclusivamente em <code className="rounded bg-muted px-1 py-0.5">backend/.env</code>.
        </p>
      </SectionCard>

      <SectionCard title="Fases implementadas">
        <ul className="flex flex-col gap-2">
          {IMPLEMENTED_PHASES.map((phase) => (
            <li key={phase} className="flex items-center gap-2 text-sm text-foreground">
              <Badge variant="secondary">OK</Badge>
              {phase}
            </li>
          ))}
          <li className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="outline">Em breve</Badge>
            Fase 6 — Prototype Builder
          </li>
        </ul>
      </SectionCard>
    </div>
  );
}
