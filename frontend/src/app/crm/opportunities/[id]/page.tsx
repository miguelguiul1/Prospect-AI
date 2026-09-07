import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getOpportunity, getTimeline } from "@/lib/api/crm";
import { listOutreach } from "@/lib/api/outreach";
import { ApiError } from "@/lib/api/client";
import { SectionCard } from "@/components/shared/section-card";
import { StageBadge } from "@/components/crm/stage-badge";
import { OpportunityActions } from "@/components/crm/opportunity-actions";
import { IntelligencePanel } from "@/components/crm/intelligence-panel";
import { ContactsPanel } from "@/components/crm/contacts-panel";
import { TimelinePanel } from "@/components/crm/timeline-panel";
import { OutreachPanel } from "@/components/crm/outreach-panel";

export const dynamic = "force-dynamic";

async function loadOpportunity(id: string) {
  try {
    return await getOpportunity(id);
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
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  try {
    const opportunity = await getOpportunity(id);
    return { title: opportunity.company_name };
  } catch {
    return { title: "Oportunidade" };
  }
}

export default async function OpportunityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const opportunity = await loadOpportunity(id);
  const [timeline, outreachHistory] = await Promise.all([
    getTimeline(id),
    listOutreach(id),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl font-semibold text-foreground">{opportunity.company_name}</h1>
          <p className="text-sm text-muted-foreground">
            {opportunity.category_name ?? "Sem categoria"}
            {opportunity.region_name ? ` · ${opportunity.region_name}` : ""}
            {" · "}
            Responsável: {opportunity.owner_name}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <StageBadge stage={opportunity.stage} />
            <span className="text-xs capitalize text-muted-foreground">{opportunity.priority}</span>
          </div>
        </div>
        <OpportunityActions opportunityId={opportunity.id} status={opportunity.status} />
      </div>

      <SectionCard title="Por que esta oportunidade é importante" description="Opportunity Score, qualidade do site e Sales Brief">
        <IntelligencePanel opportunity={opportunity} />
      </SectionCard>

      <SectionCard title="Contatos">
        <ContactsPanel opportunityId={opportunity.id} companyId={opportunity.company_id} contacts={opportunity.contacts} />
      </SectionCard>

      <SectionCard title="Outreach assistido" description="A IA sugere; você revisa, edita e envia manualmente.">
        <OutreachPanel opportunityId={opportunity.id} contacts={opportunity.contacts} history={outreachHistory} />
      </SectionCard>

      <SectionCard title="Timeline" description="Notas, tarefas e o histórico completo desta oportunidade">
        <TimelinePanel opportunityId={opportunity.id} activities={timeline} />
      </SectionCard>
    </div>
  );
}
