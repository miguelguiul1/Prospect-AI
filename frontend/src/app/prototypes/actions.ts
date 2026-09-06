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

  let id: string;
  try {
    const prototype = await createPrototype({ name, description: description || undefined });
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
