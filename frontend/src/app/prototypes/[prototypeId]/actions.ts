"use server";

import { revalidatePath } from "next/cache";
import {
  getPrototype,
  listRefinements,
  refinePrototype,
  restorePrototypeVersion,
  updatePrototype,
  type RefinementMessage,
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
  // "error" aqui é só para falha EXCEPCIONAL da chamada em si (rede,
  // 401/404/429) — nunca para "o refinamento não deu certo": esse
  // resultado é normal e vira uma mensagem no chat como qualquer outra
  // (`refinements` inclui a tentativa que falhou, com seu `errorMessage`).
  status: "ok" | "error";
  message?: string;
  refinements?: RefinementMessage[];
  components?: ComponentNode[];
}

/**
 * Refinamento por linguagem natural (Fase 9 / Prompt 12; UI de chat no
 * Prompt 13). Síncrono nesta máquina (mesmo motivo de
 * `generatePrototypeAction`, Prompt 11): a promise só resolve quando a
 * geração já terminou (sucesso OU falha) — nunca fica "pending" de
 * verdade aqui.
 *
 * Em vez de reconstruir a "mensagem" do chat manualmente a partir da
 * resposta de `/refine`, busca o histórico COMPLETO via `listRefinements`
 * depois — uma única fonte de verdade para o formato de uma mensagem
 * (histórica ou recém-criada), sem duplicar lógica de conversão em dois
 * lugares que poderiam divergir.
 */
export async function refinePrototypeAction(prototypeId: string, instruction: string): Promise<RefineResult> {
  try {
    const run = await refinePrototype(prototypeId, instruction);
    const refinements = await listRefinements(prototypeId);
    if (run.status === "failed") {
      revalidatePath(`/prototypes/${prototypeId}`);
      return { status: "ok", refinements };
    }
    const updated = await getPrototype(prototypeId);
    revalidatePath(`/prototypes/${prototypeId}`);
    return { status: "ok", refinements, components: updated.components };
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
