import Link from "next/link";
import type { Metadata } from "next";
import { Building2 } from "lucide-react";
import { getFilterOptions, listCompanies } from "@/lib/api/companies";
import { ProspectsFilters } from "@/components/prospects/prospects-filters";
import { ProspectsTable } from "@/components/prospects/prospects-table";
import { PaginationBar } from "@/components/shared/pagination-bar";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Prospects" };

const PAGE_SIZE = 20;

interface ProspectsSearchParams {
  q?: string;
  tier?: string;
  site_state?: string;
  category?: string;
  region?: string;
  audited?: string;
  sort_by?: string;
  offset?: string;
}

function buildHref(params: ProspectsSearchParams, offset: number): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (key === "offset" || !value) continue;
    search.set(key, value);
  }
  if (offset > 0) search.set("offset", String(offset));
  const qs = search.toString();
  return qs ? `/prospects?${qs}` : "/prospects";
}

export default async function ProspectsPage({
  searchParams,
}: {
  searchParams: Promise<ProspectsSearchParams>;
}) {
  const params = await searchParams;
  const offset = Number(params.offset ?? 0) || 0;
  const audited = params.audited === "true" ? true : params.audited === "false" ? false : undefined;

  const [filterOptions, page] = await Promise.all([
    getFilterOptions(),
    listCompanies({
      q: params.q,
      tier: params.tier,
      site_state: params.site_state,
      category: params.category,
      region: params.region,
      audited,
      sort_by: params.sort_by === "opportunity_score" ? "opportunity_score" : "created_at",
      limit: PAGE_SIZE,
      offset,
    }),
  ]);

  const hasActiveFilters = Boolean(
    params.q || params.tier || params.site_state || params.category || params.region || params.audited
  );

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-heading text-xl font-semibold text-foreground">Prospects</h1>
        <p className="text-sm text-muted-foreground">
          Todas as empresas descobertas, com a auditoria e o Opportunity Score mais recentes.
        </p>
      </div>

      <ProspectsFilters filterOptions={filterOptions} initialValues={params} />

      {page.items.length > 0 ? (
        <>
          <ProspectsTable items={page.items} />
          <PaginationBar
            total={page.total}
            limit={page.limit}
            offset={page.offset}
            buildHref={(o) => buildHref(params, o)}
          />
        </>
      ) : hasActiveFilters ? (
        <EmptyState
          icon={<Building2 className="size-8" />}
          title="Nenhum prospect encontrado com esses filtros."
          description="Tente remover algum filtro para ampliar a busca."
          action={
            <Button variant="outline" render={<Link href="/prospects" />}>
              Limpar filtros
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon={<Building2 className="size-8" />}
          title="Ainda não existem prospects."
          description="Execute sua primeira pesquisa para começar."
          action={<Button render={<Link href="/pesquisas/nova" />}>Nova pesquisa</Button>}
        />
      )}
    </div>
  );
}
