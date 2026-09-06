import "server-only";
import { apiGet } from "@/lib/api/client";
import type {
  CompanyDetail,
  CompanyListResponse,
  DashboardStats,
  FilterOptionsResponse,
} from "@/lib/api/types";

export interface CompanyListFilters {
  q?: string;
  tier?: string;
  min_score?: number;
  max_score?: number;
  site_state?: string;
  category?: string;
  region?: string;
  audited?: boolean;
  sort_by?: "created_at" | "opportunity_score";
  limit?: number;
  offset?: number;
}

function toQueryString(filters: CompanyListFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function listCompanies(
  filters: CompanyListFilters = {}
): Promise<CompanyListResponse> {
  return apiGet<CompanyListResponse>(`/api/companies${toQueryString(filters)}`);
}

export function getCompany(companyId: string): Promise<CompanyDetail> {
  return apiGet<CompanyDetail>(`/api/companies/${companyId}`);
}

export function getFilterOptions(): Promise<FilterOptionsResponse> {
  return apiGet<FilterOptionsResponse>("/api/companies/meta/filters");
}

export function getDashboardStats(): Promise<DashboardStats> {
  return apiGet<DashboardStats>("/api/companies/meta/stats");
}
