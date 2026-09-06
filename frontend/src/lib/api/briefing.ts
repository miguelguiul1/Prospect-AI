import "server-only";
import { apiPost } from "@/lib/api/client";
import type { SalesBriefDetail } from "@/lib/api/types";

export function generateSalesBrief(companyId: string): Promise<SalesBriefDetail> {
  return apiPost<SalesBriefDetail>(`/api/sales-brief/${companyId}`);
}
