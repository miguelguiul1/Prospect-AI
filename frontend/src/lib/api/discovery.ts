import "server-only";
import { apiGet, apiPost } from "@/lib/api/client";
import type { SearchRun, SearchRunListResponse } from "@/lib/api/types";

export interface StartSearchInput {
  region?: string;
  city?: string;
  state?: string;
  country?: string;
  category: string;
  max_results?: number;
  provider?: string;
}

export function listDiscoveryRuns(params: {
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<SearchRunListResponse> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  const qs = search.toString();
  return apiGet<SearchRunListResponse>(`/api/discovery/runs${qs ? `?${qs}` : ""}`);
}

export function getDiscoveryRun(runId: string): Promise<SearchRun> {
  return apiGet<SearchRun>(`/api/discovery/runs/${runId}`);
}

export function startDiscoverySearch(input: StartSearchInput): Promise<SearchRun> {
  return apiPost<SearchRun>("/api/discovery/search", input);
}

/** Único provider implementado nas Fases 0-4 (`GooglePlacesProvider`) —
 * nunca listar um provider fictício, mesmo como opção desabilitada. */
export const IMPLEMENTED_DISCOVERY_PROVIDERS = ["google_places"] as const;
