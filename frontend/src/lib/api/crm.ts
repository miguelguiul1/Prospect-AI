import "server-only";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api/client";
import type {
  ActivityItem,
  ActivityTypeValue,
  Contact,
  ContactValidationStatus,
  OpportunityDetail,
  OpportunityKpis,
  OpportunityListResponse,
  OpportunityPriority,
  OpportunitySummary,
  PipelineBoardResponse,
} from "@/lib/api/types";

export function createOpportunity(companyId: string, priority?: OpportunityPriority): Promise<OpportunitySummary> {
  return apiPost<OpportunitySummary>("/api/crm/opportunities", { company_id: companyId, priority });
}

export function getOpenOpportunityForCompany(companyId: string): Promise<OpportunitySummary | null> {
  return apiGet<OpportunitySummary | null>(`/api/crm/companies/${companyId}/opportunity`);
}

export function listOpportunities(params: {
  stage?: string;
  status?: string;
  priority?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<OpportunityListResponse> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") qs.set(key, String(value));
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiGet<OpportunityListResponse>(`/api/crm/opportunities${suffix}`);
}

export function getOpportunity(id: string): Promise<OpportunityDetail> {
  return apiGet<OpportunityDetail>(`/api/crm/opportunities/${id}`);
}

export function getPipelineBoard(): Promise<PipelineBoardResponse> {
  return apiGet<PipelineBoardResponse>("/api/crm/pipeline");
}

export function getKpis(): Promise<OpportunityKpis> {
  return apiGet<OpportunityKpis>("/api/crm/kpis");
}

export function changeStage(opportunityId: string, stageKey: string): Promise<OpportunitySummary> {
  return apiPatch<OpportunitySummary>(`/api/crm/opportunities/${opportunityId}/stage`, { stage_key: stageKey });
}

export function closeOpportunity(opportunityId: string, outcome: "won" | "lost", reason?: string): Promise<OpportunitySummary> {
  return apiPost<OpportunitySummary>(`/api/crm/opportunities/${opportunityId}/close`, { outcome, reason });
}

export function reopenOpportunity(opportunityId: string): Promise<OpportunitySummary> {
  return apiPost<OpportunitySummary>(`/api/crm/opportunities/${opportunityId}/reopen`, {});
}

export function getTimeline(opportunityId: string): Promise<ActivityItem[]> {
  return apiGet<ActivityItem[]>(`/api/crm/opportunities/${opportunityId}/timeline`);
}

export function listContacts(companyId: string): Promise<Contact[]> {
  return apiGet<Contact[]>(`/api/crm/contacts?company_id=${companyId}`);
}

export function createContact(payload: {
  company_id: string;
  name: string;
  role?: string;
  email?: string;
  phone?: string;
  source?: string;
}): Promise<Contact> {
  return apiPost<Contact>("/api/crm/contacts", payload);
}

export function updateContact(
  contactId: string,
  payload: Partial<{ name: string; role: string; email: string; phone: string; validation_status: ContactValidationStatus }>
): Promise<Contact> {
  return apiPut<Contact>(`/api/crm/contacts/${contactId}`, payload);
}

export function deleteContact(contactId: string): Promise<void> {
  return apiDelete(`/api/crm/contacts/${contactId}`);
}

export function createActivity(payload: {
  opportunity_id: string;
  type: ActivityTypeValue;
  title?: string;
  description?: string;
  due_at?: string;
}): Promise<ActivityItem> {
  return apiPost<ActivityItem>("/api/crm/activities", payload);
}

export function updateActivity(
  activityId: string,
  payload: Partial<{ title: string; description: string; due_at: string; completed: boolean }>
): Promise<ActivityItem> {
  return apiPut<ActivityItem>(`/api/crm/activities/${activityId}`, payload);
}

export function deleteActivity(activityId: string): Promise<void> {
  return apiDelete(`/api/crm/activities/${activityId}`);
}
