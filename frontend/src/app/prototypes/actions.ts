"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createPrototype, deletePrototype } from "@/lib/api/prototypes";
import { ApiError } from "@/lib/api/client";
import type { PrototypeActionState } from "@/app/prototypes/action-types";

export async function createPrototypeAction(
  _prev: PrototypeActionState,
  formData: FormData
): Promise<PrototypeActionState> {
  const name = String(formData.get("name") ?? "").trim();
  if (!name) {
    return { status: "error", message: "Informe um nome para o protótipo." };
  }
  const description = String(formData.get("description") ?? "").trim();

  // `company_id` é obrigatório no backend desde o Prompt 10 (Fase 9
  // precisa de contexto de empresa) — este formulário ainda não coleta um
  // (fluxo standalone herdado da Fase 6, sem seletor de empresa). Ver
  // docs/prototype-builder.md, seção "Consequência conhecida no
  // frontend": criar um protótipo aqui está temporariamente indisponível
  // até uma fase futura adicionar um ponto de entrada com contexto de
  // empresa (ex.: a partir de uma Opportunity).
  const companyId = String(formData.get("company_id") ?? "").trim();
  if (!companyId) {
    return {
      status: "error",
      message:
        "Criar um protótipo agora exige uma empresa vinculada — este formulário ainda não suporta isso. " +
        "Inicie a criação a partir da página de uma oportunidade (em breve).",
    };
  }

  let id: string;
  try {
    const prototype = await createPrototype({ name, description: description || undefined, companyId });
    id = prototype.id;
  } catch (error) {
    if (error instanceof ApiError) return { status: "error", message: error.message };
    console.error("[prototypes] erro inesperado ao criar:", error);
    return { status: "error", message: "Não foi possível criar o protótipo." };
  }

  revalidatePath("/prototypes");
  redirect(`/prototypes/${id}`);
}

export async function deletePrototypeAction(id: string): Promise<void> {
  await deletePrototype(id);
  revalidatePath("/prototypes");
}
