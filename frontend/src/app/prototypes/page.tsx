import Link from "next/link";
import type { Metadata } from "next";
import { LayoutTemplate } from "lucide-react";
import { listPrototypes } from "@/lib/api/prototypes";
import { NewPrototypeDialog } from "@/components/prototype-builder/new-prototype-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { PaginationBar } from "@/components/shared/pagination-bar";
import { formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Protótipos" };

const PAGE_SIZE = 20;

export default async function PrototypesPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const params = await searchParams;
  const offset = Number(params.offset ?? 0) || 0;
  const page = await listPrototypes({ limit: PAGE_SIZE, offset });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-xl font-semibold text-foreground">Protótipos</h1>
          <p className="text-sm text-muted-foreground">
            Transforme uma ideia em um protótipo visual dentro do Prospect AI.
          </p>
        </div>
        <NewPrototypeDialog />
      </div>

      {page.items.length === 0 ? (
        <EmptyState
          icon={<LayoutTemplate className="size-8" />}
          title="Ainda não existem protótipos."
          description="Crie o primeiro protótipo para começar a montar uma interface visual."
        />
      ) : (
        <>
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {page.items.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/prototypes/${p.id}`}
                  className="flex h-full flex-col gap-2 rounded-lg border border-border bg-card p-4 hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <p className="font-medium text-foreground">{p.name}</p>
                  <p className="line-clamp-2 flex-1 text-sm text-muted-foreground">{p.description ?? "Sem descrição."}</p>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{p.componentCount} componente{p.componentCount === 1 ? "" : "s"}</span>
                    <span>Editado em {formatDateTime(p.updatedAt)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          <PaginationBar
            total={page.total}
            limit={page.limit}
            offset={page.offset}
            buildHref={(o) => (o > 0 ? `/prototypes?offset=${o}` : "/prototypes")}
          />
        </>
      )}
    </div>
  );
}
