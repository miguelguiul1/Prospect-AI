import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Paginação real por `limit`/`offset`, sempre refletindo o `total` que o
 * backend devolveu (`GET /api/companies`, `GET /api/discovery/runs`) —
 * nunca uma paginação simulada só no frontend sobre uma página já
 * truncada. Ver docs/dashboard.md, seção "Performance".
 */
export function PaginationBar({
  total,
  limit,
  offset,
  buildHref,
}: {
  total: number;
  limit: number;
  offset: number;
  buildHref: (offset: number) => string;
}) {
  if (total <= limit) return null;

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const prevOffset = Math.max(0, offset - limit);
  const nextOffset = offset + limit;
  const hasPrev = offset > 0;
  const hasNext = nextOffset < total;

  return (
    <nav
      aria-label="Paginação"
      className="flex items-center justify-between gap-4 pt-2 text-sm text-muted-foreground"
    >
      <span>
        Página {currentPage} de {totalPages} · {total} no total
      </span>
      <div className="flex gap-2">
        {hasPrev ? (
          <Button size="sm" variant="outline" render={<Link href={buildHref(prevOffset)} />}>
            <ChevronLeft className="size-4" />
            Anterior
          </Button>
        ) : (
          <Button size="sm" variant="outline" disabled>
            <ChevronLeft className="size-4" />
            Anterior
          </Button>
        )}
        {hasNext ? (
          <Button size="sm" variant="outline" render={<Link href={buildHref(nextOffset)} />}>
            Próxima
            <ChevronRight className="size-4" />
          </Button>
        ) : (
          <Button size="sm" variant="outline" disabled>
            Próxima
            <ChevronRight className="size-4" />
          </Button>
        )}
      </div>
    </nav>
  );
}
