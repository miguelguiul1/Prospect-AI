"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { runDigitalAudit } from "@/lib/api/audit";
import { computeOpportunityScore } from "@/lib/api/scoring";
import { generateSalesBrief } from "@/lib/api/briefing";
import { createPrototype, generatePrototype } from "@/lib/api/prototypes";
import { ApiError } from "@/lib/api/client";
import type { ActionState } from "@/app/prospects/[companyId]/action-types";

function toActionState(error: unknown): ActionState {
  if (error instanceof ApiError) {
    return { status: "error", message: error.message };
  }
  console.error("[prospect-actions] erro inesperado:", error);
  return { status: "error", message: "Ocorreu um erro inesperado. Tente novamente." };
}

export async function runAuditAction(
  _prev: ActionState,
  formData: FormData
): Promise<ActionState> {
  const companyId = String(formData.get("companyId"));
  try {
    await runDigitalAudit(companyId);
  } catch (error) {
    return toActionState(error);
  }
  revalidatePath(`/prospects/${companyId}`);
  return { status: "success", message: "Auditoria executada." };
}

export async function computeScoreAction(
  _prev: ActionState,
  formData: FormData
): Promise<ActionState> {
  const companyId = String(formData.get("companyId"));
  try {
    await computeOpportunityScore(companyId);
  } catch (error) {
    return toActionState(error);
  }
  revalidatePath(`/prospects/${companyId}`);
  return { status: "success", message: "Opportunity Score calculado." };
}

export async function generateBriefAction(
  _prev: ActionState,
  formData: FormData
): Promise<ActionState> {
  const companyId = String(formData.get("companyId"));
  try {
    const brief = await generateSalesBrief(companyId);
    if (brief.status === "failed") {
      revalidatePath(`/prospects/${companyId}`);
      return {
        status: "error",
        message: brief.error_message ?? "O provider de IA não conseguiu gerar o briefing.",
      };
    }
  } catch (error) {
    return toActionState(error);
  }
  revalidatePath(`/prospects/${companyId}`);
  return { status: "success", message: "Sales Brief gerado." };
}

/**
 * Fecha a lacuna identificada no Prompt 10 (o formulário "Novo protótipo"
 * standalone não tinha seletor de empresa): cria o `Prototype` já
 * vinculado a esta empresa (nome genérico — editável depois no Builder,
 * evita precisar de um campo extra só para isto) e dispara a geração por
 * IA em seguida, no mesmo fluxo. Redireciona para o Builder já populado
 * ao terminar — nunca fica numa tela intermediária "geração concluída,
 * clique para ver".
 *
 * Diferente das outras actions desta página: NUNCA retorna
 * `{status: "success"}` no caminho feliz — `redirect()` sempre lança e
 * interrompe a execução antes disso (comportamento nativo do Next.js,
 * mesmo padrão já usado por `createPrototypeAction`).
 *
 * `POST /generate` sempre responde 202 (a requisição foi aceita e
 * processada) mesmo quando a geração falha (ex.: contexto insuficiente) —
 * mesmo padrão de `generateBriefAction` acima. Por isso o `status` do
 * resultado é checado explicitamente: nunca redireciona para um Builder
 * vazio disfarçando uma falha real como sucesso.
 */
export async function generatePrototypeAction(
  _prev: ActionState,
  formData: FormData
): Promise<ActionState> {
  const companyId = String(formData.get("companyId"));

  let prototypeId: string;
  try {
    const prototype = await createPrototype({ name: "Novo protótipo", companyId });
    prototypeId = prototype.id;
    const generation = await generatePrototype(prototypeId);
    if (generation.status === "failed") {
      revalidatePath(`/prospects/${companyId}`);
      return {
        status: "error",
        message: generation.errorMessage ?? "O provider de IA não conseguiu gerar o protótipo.",
      };
    }
  } catch (error) {
    return toActionState(error);
  }

  revalidatePath(`/prospects/${companyId}`);
  redirect(`/prototypes/${prototypeId}`);
}
