import Link from "next/link";
import type { Metadata } from "next";
import { Handshake, Users, Calendar, Trophy, XCircle, AlertTriangle, ArrowRight } from "lucide-react";
import { getKpis, listOpportunities } from "@/lib/api/crm";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { OpportunitiesList } from "@/components/crm/opportunities-list";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "CRM" };

export default async function CrmHomePage() {
  const [kpis, openOpportunities] = await Promise.all([
    getKpis(),
    listOpportunities({ status: "open", limit: 8 }),
  ]);

  const hasAny = kpis.open_count > 0 || kpis.won_count > 0 || kpis.lost_count > 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-xl font-semibold text-foreground">CRM</h1>
          <p className="text-sm text-muted-foreground">
            Suas oportunidades comerciais — a partir dos prospects já identificados.
          </p>
        </div>
        <Button size="sm" variant="outline" render={<Link href="/crm/pipeline" />}>
          Ver pipeline
          <ArrowRight className="size-4" />
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Abertas" value={kpis.open_count} hint={`${kpis.new_count} novas`} icon={<Handshake className="size-5" />} />
        <KpiCard label="Em negociação" value={kpis.in_negotiation_count} icon={<Users className="size-5" />} />
        <KpiCard label="Reuniões" value={kpis.meetings_count} icon={<Calendar className="size-5" />} />
        <KpiCard
          label="Tarefas atrasadas"
          value={kpis.overdue_tasks_count}
          hint={kpis.overdue_tasks_count > 0 ? "Precisam de atenção" : "Nenhuma pendência"}
          icon={<AlertTriangle className="size-5" />}
          className={kpis.overdue_tasks_count > 0 ? "border-amber-300 dark:border-amber-800" : undefined}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <KpiCard label="Ganhas" value={kpis.won_count} icon={<Trophy className="size-5" />} />
        <KpiCard label="Perdidas" value={kpis.lost_count} icon={<XCircle className="size-5" />} />
      </div>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-medium text-foreground">Oportunidades abertas</h2>
          {openOpportunities.total > openOpportunities.items.length ? (
            <Button size="sm" variant="ghost" render={<Link href="/crm/pipeline" />}>
              Ver todas
              <ArrowRight className="size-4" />
            </Button>
          ) : null}
        </div>

        {hasAny && openOpportunities.items.length > 0 ? (
          <OpportunitiesList items={openOpportunities.items} />
        ) : (
          <EmptyState
            icon={<Handshake className="size-8" />}
            title="Nenhuma oportunidade aberta ainda."
            description="Abra um prospect e clique em “Criar oportunidade” para começar a acompanhá-lo aqui."
            action={<Button render={<Link href="/prospects" />}>Ver prospects</Button>}
          />
        )}
      </section>
    </div>
  );
}
