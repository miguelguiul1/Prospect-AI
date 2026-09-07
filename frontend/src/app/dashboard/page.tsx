import Link from "next/link";
import type { Metadata } from "next";
import { Building2, TrendingUp, ScanSearch, Gauge, ArrowRight, Handshake, AlertTriangle } from "lucide-react";
import { getDashboardStats, listCompanies } from "@/lib/api/companies";
import { listDiscoveryRuns } from "@/lib/api/discovery";
import { getKpis } from "@/lib/api/crm";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { ProspectsTable } from "@/components/prospects/prospects-table";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { RunStatusBadge } from "@/components/badges/run-status-badge";
import { formatRelativeShort, formatScore } from "@/lib/format";

// Sempre renderizado sob demanda: os dados (KPIs, prospects, pesquisas)
// mudam a cada auditoria/score/pesquisa e nunca devem ficar presos em um
// snapshot estático gerado no build.
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const [stats, priority, recentRuns, crmKpis] = await Promise.all([
    getDashboardStats(),
    listCompanies({ sort_by: "opportunity_score", limit: 8 }),
    listDiscoveryRuns({ limit: 5 }),
    getKpis(),
  ]);

  const hasAnyProspect = stats.total_companies > 0;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-xl font-semibold text-foreground">Visão geral</h1>
        <p className="text-sm text-muted-foreground">
          Panorama de prospecção do Prospect AI — dados reais das Fases 1-4.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Prospects encontrados"
          value={stats.total_companies}
          hint={stats.total_companies === 0 ? "Nenhum prospect encontrado" : "Empresas descobertas"}
          icon={<Building2 className="size-5" />}
        />
        <KpiCard
          label="Alta oportunidade"
          value={stats.high_opportunity_companies}
          hint="Score ≥ 60 (medium_high ou high)"
          icon={<TrendingUp className="size-5" />}
        />
        <KpiCard
          label="Auditados"
          value={stats.audited_companies}
          hint={`${stats.total_companies - stats.audited_companies} sem auditoria ainda`}
          icon={<ScanSearch className="size-5" />}
        />
        <KpiCard
          label="Score médio"
          value={formatScore(stats.average_opportunity_score)}
          hint={stats.average_opportunity_score === null ? "Nenhum score calculado ainda" : "Entre os prospects já pontuados"}
          icon={<Gauge className="size-5" />}
        />
      </div>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-medium text-foreground">CRM</h2>
          <Button size="sm" variant="ghost" render={<Link href="/crm" />}>
            Ver CRM
            <ArrowRight className="size-4" />
          </Button>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <KpiCard label="Oportunidades abertas" value={crmKpis.open_count} icon={<Handshake className="size-5" />} />
          <KpiCard
            label="Tarefas atrasadas"
            value={crmKpis.overdue_tasks_count}
            icon={<AlertTriangle className="size-5" />}
            className={crmKpis.overdue_tasks_count > 0 ? "border-amber-300 dark:border-amber-800" : undefined}
          />
          <KpiCard label="Ganhas" value={crmKpis.won_count} icon={<TrendingUp className="size-5" />} />
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-medium text-foreground">Oportunidades prioritárias</h2>
          {hasAnyProspect ? (
            <Button size="sm" variant="ghost" render={<Link href="/prospects?sort_by=opportunity_score" />}>
              Ver todos
              <ArrowRight className="size-4" />
            </Button>
          ) : null}
        </div>

        {hasAnyProspect ? (
          <ProspectsTable items={priority.items} />
        ) : (
          <EmptyState
            icon={<Building2 className="size-8" />}
            title="Ainda não existem prospects."
            description="Execute sua primeira pesquisa para começar a descobrir empresas."
            action={
              <Button render={<Link href="/pesquisas/nova" />}>Nova pesquisa</Button>
            }
          />
        )}
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-medium text-foreground">Pesquisas recentes</h2>
          <Button size="sm" variant="ghost" render={<Link href="/pesquisas" />}>
            Ver todas
            <ArrowRight className="size-4" />
          </Button>
        </div>

        {recentRuns.items.length > 0 ? (
          <ul className="divide-y divide-border rounded-lg border border-border bg-card">
            {recentRuns.items.map((run) => (
              <li key={run.id}>
                <Link
                  href={`/pesquisas/${run.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {String(run.parameters.category ?? "—")}
                      {run.parameters.city || run.parameters.region ? (
                        <span className="text-muted-foreground"> · {String(run.parameters.city ?? run.parameters.region)}</span>
                      ) : null}
                    </p>
                    <p className="text-xs text-muted-foreground">{formatRelativeShort(run.created_at)}</p>
                  </div>
                  <RunStatusBadge status={run.status} />
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="Nenhuma pesquisa ainda."
            description="Toda busca de Discovery executada aparecerá aqui."
            action={<Button render={<Link href="/pesquisas/nova" />}>Nova pesquisa</Button>}
          />
        )}
      </section>
    </div>
  );
}
