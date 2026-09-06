import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getDiscoveryRun } from "@/lib/api/discovery";
import { ApiError } from "@/lib/api/client";
import { SectionCard } from "@/components/shared/section-card";
import { RunStatusBadge } from "@/components/badges/run-status-badge";
import { formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Detalhe da pesquisa" };

export default async function DiscoveryRunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  let run;
  try {
    run = await getDiscoveryRun(runId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const durationMs =
    run.started_at && run.finished_at
      ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
      : null;

  const rows: { label: string; value: string }[] = [
    { label: "Categoria", value: String(run.parameters.category ?? "—") },
    { label: "Região", value: String(run.parameters.city ?? run.parameters.region ?? "—") },
    { label: "Fonte", value: run.provider },
    { label: "Resultados brutos", value: String(run.raw_result_count ?? "—") },
    { label: "Resultados normalizados", value: String(run.normalized_result_count ?? "—") },
    { label: "Persistidos", value: String(run.persisted_count ?? "—") },
    { label: "Novas empresas", value: String(run.new_company_count ?? "—") },
    { label: "Páginas buscadas", value: String(run.pages_fetched ?? "—") },
    {
      label: "Custo estimado",
      value: run.cost_estimate !== null ? `${run.cost_estimate} ${run.cost_currency ?? ""}`.trim() : "Não estimado",
    },
    { label: "Iniciada em", value: formatDateTime(run.started_at) },
    { label: "Concluída em", value: formatDateTime(run.finished_at) },
    { label: "Duração", value: durationMs !== null ? `${(durationMs / 1000).toFixed(1)} s` : "—" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-xl font-semibold text-foreground">Run {run.id.slice(0, 8)}</h1>
        <p className="text-sm text-muted-foreground">Criada em {formatDateTime(run.created_at)}</p>
      </div>

      <SectionCard title="Execução" action={<RunStatusBadge status={run.status} />}>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          {rows.map((row) => (
            <div key={row.label} className="flex flex-col gap-0.5">
              <dt className="text-xs font-medium text-muted-foreground">{row.label}</dt>
              <dd className="text-sm text-foreground">{row.value}</dd>
            </div>
          ))}
        </dl>

        {run.error_message ? (
          <p className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {run.error_code ? `${run.error_code}: ` : ""}
            {run.error_message}
          </p>
        ) : null}
      </SectionCard>
    </div>
  );
}
