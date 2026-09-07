"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { ApiError } from "@/lib/api/client";
import * as crm from "@/lib/api/crm";
import * as outreachApi from "@/lib/api/outreach";
import type { ActionState } from "@/lib/action-types";
import type { ActivityTypeValue, OutreachChannel } from "@/lib/api/types";

function toActionState(error: unknown): ActionState {
  if (error instanceof ApiError) {
    return { status: "error", message: error.message };
  }
  console.error("[crm-actions] erro inesperado:", error);
  return { status: "error", message: "Ocorreu um erro inesperado. Tente novamente." };
}

function revalidateOpportunity(opportunityId: string) {
  revalidatePath(`/crm/opportunities/${opportunityId}`);
  revalidatePath("/crm");
  revalidatePath("/crm/pipeline");
}

/** Cria (ou reaproveita, se já existir) a Opportunity da empresa e leva o
 * usuário direto para o "centro de contexto comercial" — nunca fica só numa
 * mensagem de sucesso solta (Prompt 11, seção 6/35). */
export async function createOpportunityAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const companyId = String(formData.get("companyId"));
  let opportunityId: string;
  try {
    opportunityId = (await crm.createOpportunity(companyId)).id;
  } catch (error) {
    return toActionState(error);
  }
  revalidatePath(`/prospects/${companyId}`);
  redirect(`/crm/opportunities/${opportunityId}`);
}

export async function changeStageAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  const stageKey = String(formData.get("stageKey"));
  try {
    await crm.changeStage(opportunityId, stageKey);
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  return { status: "success", message: "Etapa atualizada." };
}

export async function closeOpportunityAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  const outcome = String(formData.get("outcome")) as "won" | "lost";
  const reason = formData.get("reason");
  try {
    await crm.closeOpportunity(opportunityId, outcome, reason ? String(reason) : undefined);
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  return { status: "success", message: outcome === "won" ? "Oportunidade marcada como ganha." : "Oportunidade marcada como perdida." };
}

export async function reopenOpportunityAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  try {
    await crm.reopenOpportunity(opportunityId);
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  return { status: "success", message: "Oportunidade reaberta." };
}

export async function createActivityAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  const type = String(formData.get("type")) as ActivityTypeValue;
  const description = String(formData.get("description") ?? "").trim();
  const title = formData.get("title");
  const dueAt = formData.get("dueAt");

  if (!description && !title) {
    return { status: "error", message: "Escreva algo antes de salvar." };
  }

  try {
    await crm.createActivity({
      opportunity_id: opportunityId,
      type,
      description: description || undefined,
      title: title ? String(title) : undefined,
      due_at: dueAt ? new Date(String(dueAt)).toISOString() : undefined,
    });
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  return { status: "success", message: type === "task" ? "Tarefa criada." : "Nota adicionada." };
}

export async function completeActivityAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  const activityId = String(formData.get("activityId"));
  const completed = formData.get("completed") === "true";
  try {
    await crm.updateActivity(activityId, { completed });
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  return { status: "success" };
}

export async function createContactAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  const companyId = String(formData.get("companyId"));
  const name = String(formData.get("name") ?? "").trim();
  if (!name) {
    return { status: "error", message: "Informe o nome do contato." };
  }
  try {
    await crm.createContact({
      company_id: companyId,
      name,
      role: String(formData.get("role") ?? "") || undefined,
      email: String(formData.get("email") ?? "") || undefined,
      phone: String(formData.get("phone") ?? "") || undefined,
      source: "manual",
    });
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  return { status: "success", message: "Contato adicionado." };
}

export async function generateOutreachAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  const channel = String(formData.get("channel")) as OutreachChannel;
  const contactId = formData.get("contactId");
  try {
    await outreachApi.generateOutreach(opportunityId, channel, contactId ? String(contactId) : undefined);
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  return { status: "success", message: "Sugestão gerada — revise antes de enviar." };
}

export async function editOutreachAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  const outreachId = String(formData.get("outreachId"));
  try {
    await outreachApi.editOutreach(outreachId, {
      subject: String(formData.get("subject") ?? ""),
      message: String(formData.get("message") ?? ""),
    });
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  return { status: "success", message: "Rascunho atualizado." };
}

export async function transitionOutreachAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const opportunityId = String(formData.get("opportunityId"));
  const outreachId = String(formData.get("outreachId"));
  const action = String(formData.get("action")) as "mark_ready" | "mark_sent" | "cancel";
  try {
    await outreachApi.transitionOutreach(outreachId, action);
  } catch (error) {
    return toActionState(error);
  }
  revalidateOpportunity(opportunityId);
  const messages: Record<string, string> = {
    mark_ready: "Marcado como pronto para envio.",
    mark_sent: "Envio manual registrado no histórico.",
    cancel: "Rascunho cancelado.",
  };
  return { status: "success", message: messages[action] };
}
