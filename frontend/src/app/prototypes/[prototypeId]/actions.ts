"use server";

import { revalidatePath } from "next/cache";
import {
  getPrototype,
  refinePrototype,
  restorePrototypeVersion,
  updatePrototype,
  type GenerationRun,
} from "@/lib/api/prototypes";
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

export interface RefineResult {
  status: "success" | "error";
  message?: string;
  run?: GenerationRun;
  components?: ComponentNode[];
}

/**
 * Refinamento por linguagem natural (Fase 9 / Prompt 12). Síncrono nesta
 * máquina (mesmo motivo de `generatePrototypeAction`, Prompt 11): a
 * promise só resolve quando a geração já terminou (sucesso OU falha) —
 * nunca fica "pending" de verdade aqui. Em caso de sucesso, busca o
 * protótipo atualizado para devolver a árvore nova ao Builder sem exigir
 * um reload completo da página.
 */
export async function refinePrototypeAction(prototypeId: string, instruction: string): Promise<RefineResult> {
  try {
    const run = await refinePrototype(prototypeId, instruction);
    if (run.status === "failed") {
      return { status: "error", message: run.errorMessage ?? "Não foi possível aplicar o refinamento.", run };
    }
    const updated = await getPrototype(prototypeId);
    revalidatePath(`/prototypes/${prototypeId}`);
    return { status: "success", run, components: updated.components };
  } catch (error) {
    if (error instanceof ApiError) {
      return { status: "error", message: error.message };
    }
    console.error("[prototypes] erro inesperado ao refinar:", error);
    return { status: "error", message: "Não foi possível aplicar o refinamento." };
  }
}

export interface RestoreResult {
  status: "success" | "error";
  message?: string;
  components?: ComponentNode[];
}

export async function restoreVersionAction(prototypeId: string, versionId: string): Promise<RestoreResult> {
  try {
    const restored = await restorePrototypeVersion(prototypeId, versionId);
    revalidatePath(`/prototypes/${prototypeId}`);
    revalidatePath(`/prototypes/${prototypeId}/versions`);
    return { status: "success", components: restored.components };
  } catch (error) {
    if (error instanceof ApiError) {
      return { status: "error", message: error.message };
    }
    console.error("[prototypes] erro inesperado ao restaurar versão:", error);
    return { status: "error", message: "Não foi possível restaurar esta versão." };
  }
}
