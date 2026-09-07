import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ScanSearch, Gauge, Handshake, ArrowRight } from "lucide-react";
import { getCompany } from "@/lib/api/companies";
import { getOpenOpportunityForCompany } from "@/lib/api/crm";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/prospect-detail/action-button";
import { runAuditAction, computeScoreAction } from "@/app/prospects/[companyId]/actions";
import { createOpportunityAction } from "@/app/crm/actions";
import { IdentitySection } from "@/components/prospect-detail/identity-section";
import { DiscoverySection } from "@/components/prospect-detail/discovery-section";
import { WebsiteSection } from "@/components/prospect-detail/website-section";
import { WebsiteQualitySection } from "@/components/prospect-detail/website-quality-section";
import { OpportunitySection } from "@/components/prospect-detail/opportunity-section";
import { BreakdownSection } from "@/components/prospect-detail/breakdown-section";
import { EvidenceSection } from "@/components/prospect-detail/evidence-section";
import { SalesBriefSection } from "@/components/prospect-detail/sales-brief-section";
import { PrototypeSection } from "@/components/prospect-detail/prototype-section";

export const dynamic = "force-dynamic";

async function loadCompany(companyId: string) {
  try {
    return await getCompany(companyId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ companyId: string }>;
}): Promise<Metadata> {
  const { companyId } = await params;
  try {
    const company = await getCompany(companyId);
    return { title: company.canonical_name };
  } catch {
    return { title: "Prospect" };
  }
}

export default async function ProspectDetailPage({
  params,
}: {
  params: Promise<{ companyId: string }>;
}) {
  const { companyId } = await params;
  const [company, openOpportunity] = await Promise.all([
    loadCompany(companyId),
    getOpenOpportunityForCompany(companyId),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl font-semibold text-foreground">{company.canonical_name}</h1>
          <p className="text-sm text-muted-foreground">
            {company.category_name ?? "Sem categoria"}
            {company.region_name ? ` · ${company.region_name}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <ActionButton
            action={runAuditAction}
            companyId={company.id}
            label={company.latest_audit ? "Rodar nova auditoria" : "Rodar auditoria"}
            pendingLabel="Auditando…"
            icon={<ScanSearch className="size-4" />}
            variant="outline"
          />
          <ActionButton
            action={computeScoreAction}
            companyId={company.id}
            label={company.latest_score ? "Recalcular score" : "Calcular score"}
            pendingLabel="Calculando…"
            icon={<Gauge className="size-4" />}
            variant="outline"
          />
          {openOpportunity ? (
            <Button size="sm" render={<Link href={`/crm/opportunities/${openOpportunity.id}`} />}>
              <Handshake className="size-4" />
              Abrir no CRM
              <ArrowRight className="size-4" />
            </Button>
          ) : (
            <ActionButton
              action={createOpportunityAction}
              companyId={company.id}
              label="Criar oportunidade"
              pendingLabel="Criando…"
              icon={<Handshake className="size-4" />}
            />
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <IdentitySection company={company} />
        <DiscoverySection sources={company.sources} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <WebsiteSection audit={company.latest_audit} />
        <WebsiteQualitySection audit={company.latest_audit} />
      </div>

      <OpportunitySection score={company.latest_score} />
      <BreakdownSection breakdown={company.latest_score?.breakdown ?? null} />
      <EvidenceSection evidence={company.evidence} />
      <SalesBriefSection companyId={company.id} brief={company.latest_brief} hasScore={Boolean(company.latest_score)} />
      <PrototypeSection companyId={company.id} hasOpportunity={Boolean(openOpportunity)} />
    </div>
  );
}
