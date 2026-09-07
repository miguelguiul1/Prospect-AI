import "server-only";
import { apiGet, apiPatch, apiPost } from "@/lib/api/client";
import type { OutreachChannel, OutreachMessage } from "@/lib/api/types";

export function generateOutreach(
  opportunityId: string,
  channel: OutreachChannel,
  contactId?: string
): Promise<OutreachMessage> {
  return apiPost<OutreachMessage>(`/api/crm/opportunities/${opportunityId}/outreach/generate`, {
    channel,
    contact_id: contactId,
  });
}

export function listOutreach(opportunityId: string): Promise<OutreachMessage[]> {
  return apiGet<OutreachMessage[]>(`/api/crm/opportunities/${opportunityId}/outreach`);
}

export function editOutreach(outreachId: string, payload: { subject?: string; message?: string }): Promise<OutreachMessage> {
  return apiPatch<OutreachMessage>(`/api/crm/outreach/${outreachId}`, payload);
}

export function transitionOutreach(
  outreachId: string,
  action: "mark_ready" | "mark_sent" | "cancel"
): Promise<OutreachMessage> {
  return apiPost<OutreachMessage>(`/api/crm/outreach/${outreachId}/transition`, { action });
}
