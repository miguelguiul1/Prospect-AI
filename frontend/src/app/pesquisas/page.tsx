import Link from "next/link";
import type { Metadata } from "next";
import { Search, Plus } from "lucide-react";
import { listDiscoveryRuns } from "@/lib/api/discovery";
import { RunStatusBadge } from "@/components/badges/run-status-badge";
import { PaginationBar } from "@/components/shared/pagination-bar";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Pesquisas" };

const PAGE_SIZE = 20;

export default async function PesquisasPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string; status?: string }>;
}) {
  const params = await searchParams;
  const offset = Number(params.offset ?? 0) || 0;

  const page = await listDiscoveryRuns({ status: params.status, limit: PAGE_SIZE, offset });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-xl font-semibold text-foreground">Pesquisas</h1>
          <p className="text-sm text-muted-foreground">Histórico de buscas de Discovery (Fase 1).</p>
        </div>
        <Button render={<Link href="/pesquisas/nova" />}>
          <Plus className="size-4" />
          Nova pesquisa
        </Button>
      </div>

      {page.items.length === 0 ? (
        <EmptyState
          icon={<Search className="size-8" />}
          title="Nenhuma pesquisa ainda."
          description="Execute sua primeira pesquisa para descobrir prospects."
          action={<Button render={<Link href="/pesquisas/nova" />}>Nova pesquisa</Button>}
        />
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="[&_tr]:border-b">
                <tr className="text-left text-foreground">
                  <th className="h-10 px-3 font-medium">Categoria</th>
                  <th className="h-10 px-3 font-medium">Região</th>
                  <th className="h-10 px-3 font-medium">Status</th>
                  <th className="h-10 px-3 text-right font-medium">Encontrados</th>
                  <th className="h-10 px-3 text-right font-medium">Novos</th>
                  <th className="h-10 px-3 font-medium">Quando</th>
                </tr>
              </thead>
              <tbody className="[&_tr:last-child]:border-0">
                {page.items.map((run) => (
                  <tr key={run.id} className="border-b transition-colors hover:bg-muted/50">
                    <td className="p-3">
                      <Link href={`/pesquisas/${run.id}`} className="font-medium text-foreground hover:underline">
                        {String(run.parameters.category ?? "—")}
                      </Link>
                    </td>
                    <td className="p-3 text-muted-foreground">
                      {String(run.parameters.city ?? run.parameters.region ?? "—")}
                    </td>
                    <td className="p-3">
                      <RunStatusBadge status={run.status} />
                    </td>
                    <td className="p-3 text-right font-mono tabular-nums">{run.persisted_count ?? "—"}</td>
                    <td className="p-3 text-right font-mono tabular-nums">{run.new_company_count ?? "—"}</td>
                    <td className="p-3 text-muted-foreground">{formatDateTime(run.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationBar
            total={page.total}
            limit={page.limit}
            offset={page.offset}
            buildHref={(o) => (o > 0 ? `/pesquisas?offset=${o}` : "/pesquisas")}
          />
        </>
      )}
    </div>
  );
}
