"use server";

import { revalidatePath } from "next/cache";
import { runDigitalAudit } from "@/lib/api/audit";
import { computeOpportunityScore } from "@/lib/api/scoring";
import { generateSalesBrief } from "@/lib/api/briefing";
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
