"use client";

import { useRef } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { FilterOptionsResponse } from "@/lib/api/types";
import { SITE_STATE_LABEL, TIER_LABEL } from "@/lib/format";

const SELECT_CLASS =
  "h-8 rounded-lg border border-input bg-background px-2.5 text-sm text-foreground shadow-xs transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none dark:bg-input/30";

export interface ProspectsFiltersValue {
  q?: string;
  tier?: string;
  site_state?: string;
  category?: string;
  region?: string;
  audited?: string;
}

/**
 * Formulário GET nativo — cada filtro é um `name` de query string, sem
 * estado de cliente duplicado. Funciona mesmo com JavaScript desabilitado
 * (o botão "Filtrar" ainda submete); os `onChange` abaixo só melhoram a UX
 * enviando o formulário assim que um select muda, sem exigir um clique
 * extra.
 */
export function ProspectsFilters({
  filterOptions,
  initialValues,
}: {
  filterOptions: FilterOptionsResponse;
  initialValues: ProspectsFiltersValue;
}) {
  const formRef = useRef<HTMLFormElement>(null);

  return (
    <form
      ref={formRef}
      method="get"
      className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-3"
      aria-label="Filtros de prospects"
    >
      <div className="flex min-w-40 flex-1 flex-col gap-1">
        <label htmlFor="q" className="text-xs font-medium text-muted-foreground">
          Buscar por nome
        </label>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input id="q" name="q" defaultValue={initialValues.q} placeholder="Ex.: Barbearia Central" className="pl-8" />
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="tier" className="text-xs font-medium text-muted-foreground">
          Classificação
        </label>
        <select
          id="tier"
          name="tier"
          defaultValue={initialValues.tier ?? ""}
          onChange={() => formRef.current?.requestSubmit()}
          className={SELECT_CLASS}
        >
          <option value="">Todas</option>
          {Object.entries(TIER_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="site_state" className="text-xs font-medium text-muted-foreground">
          Website
        </label>
        <select
          id="site_state"
          name="site_state"
          defaultValue={initialValues.site_state ?? ""}
          onChange={() => formRef.current?.requestSubmit()}
          className={SELECT_CLASS}
        >
          <option value="">Todos</option>
          {Object.entries(SITE_STATE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="category" className="text-xs font-medium text-muted-foreground">
          Segmento
        </label>
        <select
          id="category"
          name="category"
          defaultValue={initialValues.category ?? ""}
          onChange={() => formRef.current?.requestSubmit()}
          className={SELECT_CLASS}
        >
          <option value="">Todos</option>
          {filterOptions.categories.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="region" className="text-xs font-medium text-muted-foreground">
          Região
        </label>
        <select
          id="region"
          name="region"
          defaultValue={initialValues.region ?? ""}
          onChange={() => formRef.current?.requestSubmit()}
          className={SELECT_CLASS}
        >
          <option value="">Todas</option>
          {filterOptions.regions.map((r) => (
            <option key={r.name} value={r.name}>
              {r.state ? `${r.name}, ${r.state}` : r.name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="audited" className="text-xs font-medium text-muted-foreground">
          Auditoria
        </label>
        <select
          id="audited"
          name="audited"
          defaultValue={initialValues.audited ?? ""}
          onChange={() => formRef.current?.requestSubmit()}
          className={SELECT_CLASS}
        >
          <option value="">Todos</option>
          <option value="true">Auditados</option>
          <option value="false">Não auditados</option>
        </select>
      </div>

      <div className="flex gap-2">
        <Button type="submit" size="sm" variant="secondary">
          Filtrar
        </Button>
        <Button type="button" size="sm" variant="ghost" render={<Link href="/prospects" />}>
          Limpar
        </Button>
      </div>
    </form>
  );
}
