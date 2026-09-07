/**
 * Tipos espelhando exatamente as respostas da API do backend (Fases 0-4).
 * Nenhum campo aqui é inventado — cada um corresponde a um campo real dos
 * response models em `backend/app/api/routes/*.py`. Se um campo não existe
 * no backend, ele não existe aqui.
 */

export type OpportunityTier =
  | "high"
  | "medium_high"
  | "medium"
  | "low"
  | "very_low";

export type ConfidenceLevel = "high" | "medium" | "low";

export type DataState =
  | "confirmed"
  | "not_detected"
  | "inconclusive"
  | "inaccessible"
  | "not_checked"
  | "stale";

export type AuditStatus = "pending" | "running" | "completed" | "failed";

export type SearchRunStatus =
  | "pending"
  | "running"
  | "completed"
  | "partially_completed"
  | "failed"
  | "cancelled";

export type SalesBriefStatus = "completed" | "failed";

export type EvidenceMethod =
  | "structured_field"
  | "heuristic_match"
  | "inference"
  | "manual";

// --- /api/companies ---------------------------------------------------

export interface CompanyListItem {
  id: string;
  canonical_name: string;
  category_name: string | null;
  category_slug: string | null;
  region_name: string | null;
  region_state: string | null;
  created_at: string;
  has_audit: boolean;
  audit_status: AuditStatus | null;
  site_state: DataState | null;
  website_quality_score: number | null;
  opportunity_score: number | null;
  opportunity_tier: OpportunityTier | null;
  opportunity_confidence: ConfidenceLevel | null;
}

export interface CompanyListResponse {
  items: CompanyListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DashboardStats {
  total_companies: number;
  audited_companies: number;
  high_opportunity_companies: number;
  average_opportunity_score: number | null;
}

export interface FilterOptionsResponse {
  categories: { slug: string; name: string }[];
  regions: { name: string; state: string | null }[];
}

export interface CompanySource {
  id: string;
  source: string;
  external_id: string;
  source_url: string | null;
  latitude: number | null;
  longitude: number | null;
  confidence: ConfidenceLevel;
  first_seen_at: string;
  last_seen_at: string;
}

export interface EvidenceItem {
  id: string;
  field: string;
  value: string | null;
  state: DataState;
  source: string;
  source_url: string | null;
  method: EvidenceMethod;
  confidence: ConfidenceLevel;
  collected_at: string;
}

export interface WebsiteQualityDetail {
  score: number | null;
  components: Record<string, number> | null;
  confidence: ConfidenceLevel | null;
  limitations: string[] | null;
  signals: Record<string, unknown> | null;
}

export interface AuditSnapshotDetail {
  id: string;
  run_id: string;
  status: AuditStatus;
  site_state: DataState | null;
  website_url: string | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  website_quality: WebsiteQualityDetail | null;
}

export interface ScoreDimension {
  raw: number | null;
  weight: number;
  contribution: number | null;
  reason: string;
  evidence_refs: { field: string; value: unknown; evidence_id: string | null }[];
}

export interface OpportunityBreakdown {
  scoring_version: string;
  dimensions: Record<string, ScoreDimension>;
  final_score: number | null;
  available_weight: number;
  available_dimension_count?: number;
}

export interface OpportunityScoreDetail {
  id: string;
  score: number | null;
  tier: OpportunityTier | null;
  confidence: ConfidenceLevel | null;
  scoring_version: string;
  breakdown: OpportunityBreakdown | null;
  created_at: string;
  updated_at: string;
}

export interface SalesBriefContent {
  summary: string;
  opportunity: string;
  why_this_prospect: string;
  digital_gaps: string;
  suggested_angle: string;
  talking_points: string[];
  risks_and_caveats: string;
  evidence_used: string[];
}

export interface SalesBriefDetail {
  id: string;
  status: SalesBriefStatus;
  content: SalesBriefContent | null;
  provider: string | null;
  model: string | null;
  error_code: string | null;
  error_message: string | null;
  generated_at: string;
}

export interface CompanyDetail {
  id: string;
  canonical_name: string;
  status: string;
  category_name: string | null;
  category_slug: string | null;
  region_name: string | null;
  region_state: string | null;
  created_at: string;
  sources: CompanySource[];
  evidence: EvidenceItem[];
  latest_audit: AuditSnapshotDetail | null;
  latest_score: OpportunityScoreDetail | null;
  latest_brief: SalesBriefDetail | null;
}

// --- /api/discovery -----------------------------------------------------

export interface SearchRun {
  id: string;
  status: SearchRunStatus;
  provider: string;
  parameters: Record<string, unknown>;
  raw_result_count: number | null;
  normalized_result_count: number | null;
  persisted_count: number | null;
  new_company_count: number | null;
  pages_fetched: number | null;
  error_code: string | null;
  error_message: string | null;
  cost_estimate: number | null;
  cost_currency: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  execution_mode?: string | null;
}

export interface SearchRunListResponse {
  items: SearchRun[];
  total: number;
  limit: number;
  offset: number;
}

// --- /api/auth (Fase 7) --------------------------------------------------

export interface UserResponse {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserResponse;
}

// --- /api/crm (Fase 7) ----------------------------------------------------

export type OpportunityStatus = "open" | "won" | "lost" | "archived";
export type OpportunityPriority = "low" | "medium" | "high";
export type ContactValidationStatus = "unverified" | "verified" | "invalid";
export type ActivityTypeValue =
  | "note"
  | "task"
  | "call"
  | "meeting"
  | "email"
  | "whatsapp"
  | "outreach"
  | "stage_change"
  | "ownership_changed"
  | "system";
export type ActivityStatusValue = "open" | "done";

export interface PipelineStage {
  id: string;
  key: string;
  name: string;
  order: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface OpportunitySummary {
  id: string;
  company_id: string;
  company_name: string;
  category_name: string | null;
  region_name: string | null;
  owner_id: string;
  owner_name: string;
  stage: PipelineStage;
  status: OpportunityStatus;
  priority: OpportunityPriority;
  opportunity_score: number | null;
  opportunity_tier: OpportunityTier | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface OpportunityListResponse {
  items: OpportunitySummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface PipelineBoardColumn {
  stage: PipelineStage;
  opportunities: OpportunitySummary[];
}

export interface PipelineBoardResponse {
  columns: PipelineBoardColumn[];
}

export interface OpportunityKpis {
  open_count: number;
  new_count: number;
  in_negotiation_count: number;
  meetings_count: number;
  won_count: number;
  lost_count: number;
  overdue_tasks_count: number;
}

export interface ContactSummary {
  id: string;
  name: string;
  role: string | null;
  email: string | null;
  phone: string | null;
  validation_status: ContactValidationStatus;
}

export interface Contact extends ContactSummary {
  company_id: string;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface ActivityItem {
  id: string;
  opportunity_id?: string;
  type: ActivityTypeValue;
  title: string | null;
  description: string | null;
  status: ActivityStatusValue | null;
  due_at: string | null;
  completed_at: string | null;
  context?: Record<string, unknown> | null;
  created_by?: string;
  created_at: string;
}

export interface OpportunityDetail {
  id: string;
  status: OpportunityStatus;
  priority: OpportunityPriority;
  stage: PipelineStage;
  owner_id: string;
  owner_name: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;

  company_id: string;
  company_name: string;
  category_name: string | null;
  region_name: string | null;
  website_url: string | null;
  site_state: DataState | null;
  website_quality_score: number | null;
  opportunity_score: number | null;
  opportunity_tier: OpportunityTier | null;
  opportunity_confidence: ConfidenceLevel | null;
  opportunity_breakdown: OpportunityBreakdown | null;
  sales_brief_status: SalesBriefStatus | null;
  sales_brief_content: SalesBriefContent | null;

  contacts: ContactSummary[];
  recent_activities: ActivityItem[];
}

// --- /api/crm outreach (Fase 7) -------------------------------------------

export type OutreachChannel = "email" | "whatsapp" | "other";
export type OutreachStatus = "draft" | "ready" | "sent_manually" | "cancelled";

export interface OutreachMessage {
  id: string;
  opportunity_id: string;
  contact_id: string | null;
  channel: OutreachChannel;
  status: OutreachStatus;
  subject: string | null;
  message: string | null;
  rationale: string | null;
  evidence_ids: string[];
  generated_by_ai: boolean;
  created_at: string;
  updated_at: string;
}
