import type { Metadata } from "next";
import { NewSearchForm } from "@/components/discovery/new-search-form";

export const metadata: Metadata = { title: "Nova pesquisa" };

export default function NovaPesquisaPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-xl font-semibold text-foreground">Nova pesquisa</h1>
        <p className="text-sm text-muted-foreground">
          Descobre empresas de uma categoria em uma região via Google Places (Fase 1).
        </p>
      </div>
      <NewSearchForm />
    </div>
  );
}
