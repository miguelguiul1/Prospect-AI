"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { startDiscoverySearch } from "@/lib/api/discovery";
import { ApiError } from "@/lib/api/client";
import type { NewSearchState } from "@/app/pesquisas/nova/action-types";

export async function startSearchAction(
  _prev: NewSearchState,
  formData: FormData
): Promise<NewSearchState> {
  const category = String(formData.get("category") ?? "").trim();
  if (!category) {
    return { status: "error", message: "Informe uma categoria." };
  }

  const city = String(formData.get("city") ?? "").trim();
  const region = String(formData.get("region") ?? "").trim();
  if (!city && !region) {
    return { status: "error", message: "Informe uma cidade ou região." };
  }

  const maxResultsRaw = String(formData.get("max_results") ?? "20");
  const maxResults = Number(maxResultsRaw) || 20;

  let runId: string;
  try {
    const run = await startDiscoverySearch({
      category,
      city: city || undefined,
      region: region || undefined,
      state: String(formData.get("state") ?? "").trim() || undefined,
      country: String(formData.get("country") ?? "BR").trim() || "BR",
      max_results: maxResults,
    });
    runId = run.id;
  } catch (error) {
    if (error instanceof ApiError) {
      return { status: "error", message: error.message };
    }
    console.error("[nova-pesquisa] erro inesperado:", error);
    return { status: "error", message: "Não foi possível iniciar a pesquisa. Tente novamente." };
  }

  revalidatePath("/pesquisas");
  redirect(`/pesquisas/${runId}`);
}
