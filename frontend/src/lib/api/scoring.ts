import "server-only";
import { apiPost } from "@/lib/api/client";
import type { OpportunityScoreDetail } from "@/lib/api/types";

export function computeOpportunityScore(companyId: string): Promise<OpportunityScoreDetail> {
  return apiPost<OpportunityScoreDetail>(`/api/scoring/${companyId}`);
}
