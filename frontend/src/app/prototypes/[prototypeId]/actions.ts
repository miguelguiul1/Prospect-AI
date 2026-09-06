"use server";

import { revalidatePath } from "next/cache";
import { updatePrototype } from "@/lib/api/prototypes";
import { ApiError } from "@/lib/api/client";
import type { ComponentNode } from "@/lib/prototype/types";

export interface SaveResult {
  status: "success" | "error";
  message?: string;
  updatedAt?: string;
}

export async function savePrototypeAction(
  prototypeId: string,
  input: { name: string; components: ComponentNode[] }
): Promise<SaveResult> {
  try {
    const updated = await updatePrototype(prototypeId, { name: input.name, components: input.components });
    revalidatePath(`/prototypes/${prototypeId}`);
    revalidatePath("/prototypes");
    return { status: "success", updatedAt: updated.updatedAt };
  } catch (error) {
    if (error instanceof ApiError) {
      return { status: "error", message: error.message };
    }
    console.error("[prototypes] erro inesperado ao salvar:", error);
    return { status: "error", message: "Não foi possível salvar o protótipo." };
  }
}
