import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ArrowLeft, Eye, History } from "lucide-react";
import { getPrototype, listPrototypeVersions } from "@/lib/api/prototypes";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ prototypeId: string }>;
}): Promise<Metadata> {
  const { prototypeId } = await params;
  try {
    const prototype = await getPrototype(prototypeId);
    return { title: `Versões — ${prototype.name}` };
  } catch {
    return { title: "Versões" };
  }
}

/**
 * Histórico de versões (Fase 9 / Prompt 12) — lista simples, mais recente
 * primeiro. NÃO inclui edições manuais do Builder (só geração inicial,
 * refinamentos e restaurações — ver docstring de `PrototypeVersion` no
 * backend para o porquê dessa decisão de escopo).
 */
export default async function PrototypeVersionsPage({
  params,
}: {
  params: Promise<{ prototypeId: string }>;
}) {
  const { prototypeId } = await params;

  let prototype;
  let versions;
  try {
    [prototype, versions] = await Promise.all([getPrototype(prototypeId), listPrototypeVersions(prototypeId)]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Button size="icon" variant="ghost" render={<Link href={`/prototypes/${prototypeId}`} aria-label="Voltar para o protótipo" />}>
          <ArrowLeft className="size-4" />
        </Button>
        <div>
          <h1 className="font-heading text-xl font-semibold text-foreground">Versões — {prototype.name}</h1>
          <p className="text-sm text-muted-foreground">
            Cada geração por IA, refinamento e restauração cria uma versão nova — nunca sobrescreve uma anterior.
          </p>
        </div>
      </div>

      {versions.length === 0 ? (
        <EmptyState
          icon={<History className="size-8" />}
          title="Ainda não há nenhuma versão."
          description="Gere o protótipo por IA para começar o histórico de versões."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {versions.map((v) => (
            <li key={v.id}>
              <Link
                href={`/prototypes/${prototypeId}/versions/${v.id}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3 hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="flex items-center gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground">
                    v{v.versionNumber}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-foreground">{v.description}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(v.createdAt)} · {v.componentCount} componente{v.componentCount === 1 ? "" : "s"}
                    </p>
                  </div>
                </div>
                <Eye className="size-4 shrink-0 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
