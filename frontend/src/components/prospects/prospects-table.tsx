import Link from "next/link";
import { ChevronRight } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TierBadge } from "@/components/badges/tier-badge";
import { ConfidenceBadge } from "@/components/badges/confidence-badge";
import { SiteStateBadge } from "@/components/badges/site-state-badge";
import { formatScore } from "@/lib/format";
import type { CompanyListItem } from "@/lib/api/types";

function locationLabel(item: CompanyListItem): string {
  if (!item.region_name) return "—";
  return item.region_state ? `${item.region_name}, ${item.region_state}` : item.region_name;
}

/** Tabela em telas médias+, lista de cards em telas pequenas — os mesmos
 * dados, duas apresentações (nunca dados diferentes por breakpoint). */
export function ProspectsTable({ items }: { items: CompanyListItem[] }) {
  return (
    <>
      <div className="hidden overflow-hidden rounded-lg border border-border md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Empresa</TableHead>
              <TableHead>Segmento</TableHead>
              <TableHead>Localização</TableHead>
              <TableHead>Website</TableHead>
              <TableHead className="text-right">Qualidade</TableHead>
              <TableHead className="text-right">Opportunity</TableHead>
              <TableHead>Classificação</TableHead>
              <TableHead>Confiança</TableHead>
              <TableHead className="sr-only">Ação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id} className="cursor-pointer">
                <TableCell className="whitespace-normal font-medium text-foreground">
                  <Link href={`/prospects/${item.id}`} className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm">
                    {item.canonical_name}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">{item.category_name ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground">{locationLabel(item)}</TableCell>
                <TableCell>
                  <SiteStateBadge state={item.site_state} />
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {formatScore(item.website_quality_score)}
                </TableCell>
                <TableCell className="text-right font-mono font-medium tabular-nums">
                  {formatScore(item.opportunity_score)}
                </TableCell>
                <TableCell>
                  <TierBadge tier={item.opportunity_tier} />
                </TableCell>
                <TableCell>
                  <ConfidenceBadge confidence={item.opportunity_confidence} />
                </TableCell>
                <TableCell>
                  <Link
                    href={`/prospects/${item.id}`}
                    aria-label={`Abrir detalhe de ${item.canonical_name}`}
                    className="flex items-center justify-center text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                  >
                    <ChevronRight className="size-4" />
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ul className="flex flex-col gap-3 md:hidden">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              href={`/prospects/${item.id}`}
              className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-foreground">{item.canonical_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {item.category_name ?? "Sem categoria"} · {locationLabel(item)}
                  </p>
                </div>
                <span className="font-mono text-lg font-semibold tabular-nums text-foreground">
                  {formatScore(item.opportunity_score)}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <SiteStateBadge state={item.site_state} />
                <TierBadge tier={item.opportunity_tier} />
                <ConfidenceBadge confidence={item.opportunity_confidence} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
