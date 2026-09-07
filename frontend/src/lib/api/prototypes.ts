import "server-only";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api/client";
import type { ComponentNode } from "@/lib/prototype/types";

interface PrototypeSummaryResponse {
  id: string;
  name: string;
  description: string | null;
  company_id: string | null;
  component_count: number;
  created_at: string;
  updated_at: string;
}

interface PrototypeListResponse {
  items: PrototypeSummaryResponse[];
  total: number;
  limit: number;
  offset: number;
}

interface PrototypeDetailResponse {
  id: string;
  name: string;
  description: string | null;
  company_id: string | null;
  components: BackendComponentNode[];
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface BackendComponentNode {
  id: string;
  type: string;
  parent_id: string | null;
  order: number;
  props: Record<string, string | number | boolean | null>;
  styles: Record<string, string | number | boolean | null>;
}

function toComponentNode(node: BackendComponentNode): ComponentNode {
  return {
    id: node.id,
    type: node.type as ComponentNode["type"],
    parentId: node.parent_id,
    order: node.order,
    props: node.props,
    styles: node.styles,
  };
}

function toBackendComponentNode(node: ComponentNode): BackendComponentNode {
  return {
    id: node.id,
    type: node.type,
    parent_id: node.parentId,
    order: node.order,
    props: node.props,
    styles: node.styles,
  };
}

export interface PrototypeSummary {
  id: string;
  name: string;
  description: string | null;
  componentCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface PrototypeDetail {
  id: string;
  name: string;
  description: string | null;
  components: ComponentNode[];
  createdAt: string;
  updatedAt: string;
}

export async function listPrototypes(params: { limit?: number; offset?: number } = {}): Promise<{
  items: PrototypeSummary[];
  total: number;
  limit: number;
  offset: number;
}> {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  const qs = search.toString();
  const response = await apiGet<PrototypeListResponse>(`/api/prototypes${qs ? `?${qs}` : ""}`);
  return {
    items: response.items.map((p) => ({
      id: p.id,
      name: p.name,
      description: p.description,
      componentCount: p.component_count,
      createdAt: p.created_at,
      updatedAt: p.updated_at,
    })),
    total: response.total,
    limit: response.limit,
    offset: response.offset,
  };
}

export async function getPrototype(id: string): Promise<PrototypeDetail> {
  const response = await apiGet<PrototypeDetailResponse>(`/api/prototypes/${id}`);
  return {
    id: response.id,
    name: response.name,
    description: response.description,
    components: response.components.map(toComponentNode),
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  };
}

/**
 * `company_id` é obrigatório no backend desde o Prompt 10 (Fase 9 precisa
 * saber de qual empresa puxar contexto). `NewPrototypeDialog`
 * (`components/prototype-builder/new-prototype-dialog.tsx`, fluxo
 * standalone herdado da Fase 6) continua sem um seletor de empresa —
 * chamar esta função a partir de lá sem `companyId` ainda retorna 422 do
 * backend. O ponto de entrada real com contexto de empresa chegou no
 * Prompt 11: `generatePrototypeAction`
 * (`app/prospects/[companyId]/actions.ts`) chama esta função a partir da
 * página de detalhe do prospect, onde `companyId` já está disponível.
 */
export async function createPrototype(input: {
  name: string;
  description?: string;
  companyId: string;
}): Promise<PrototypeDetail> {
  const response = await apiPost<PrototypeDetailResponse>("/api/prototypes", {
    name: input.name,
    description: input.description,
    company_id: input.companyId,
  });
  return {
    id: response.id,
    name: response.name,
    description: response.description,
    components: response.components.map(toComponentNode),
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  };
}

export async function updatePrototype(
  id: string,
  input: { name?: string; description?: string; components?: ComponentNode[] }
): Promise<PrototypeDetail> {
  const response = await apiPut<PrototypeDetailResponse>(`/api/prototypes/${id}`, {
    name: input.name,
    description: input.description,
    components: input.components?.map(toBackendComponentNode),
  });
  return {
    id: response.id,
    name: response.name,
    description: response.description,
    components: response.components.map(toComponentNode),
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  };
}

export async function deletePrototype(id: string): Promise<void> {
  await apiDelete(`/api/prototypes/${id}`);
}

interface GenerationRunResponse {
  id: string;
  prototype_id: string;
  company_id: string;
  status: "pending" | "succeeded" | "failed";
  provider: string | null;
  model: string | null;
  error_code: string | null;
  error_message: string | null;
  grounding_warnings: string[] | null;
  created_at: string;
  completed_at: string | null;
  execution_mode: string | null;
}

export interface GenerationRun {
  id: string;
  prototypeId: string;
  status: "pending" | "succeeded" | "failed";
  errorMessage: string | null;
  groundingWarnings: string[] | null;
  createdAt: string;
  completedAt: string | null;
}

function toGenerationRun(response: GenerationRunResponse): GenerationRun {
  return {
    id: response.id,
    prototypeId: response.prototype_id,
    status: response.status,
    errorMessage: response.error_message,
    groundingWarnings: response.grounding_warnings,
    createdAt: response.created_at,
    completedAt: response.completed_at,
  };
}

/** Dispara a geração por IA (Fase 9 / Prompt 11) — síncrona nesta máquina
 * (sem Redis real, ver docs/production-readiness.md), mas o contrato já
 * é o de uma operação que PODE levar alguns segundos: o chamador deve
 * mostrar um estado de carregamento enquanto aguarda esta promise. */
export async function generatePrototype(prototypeId: string): Promise<GenerationRun> {
  const response = await apiPost<GenerationRunResponse>(`/api/prototypes/${prototypeId}/generate`);
  return toGenerationRun(response);
}

export async function getGeneration(prototypeId: string, generationId: string): Promise<GenerationRun> {
  const response = await apiGet<GenerationRunResponse>(
    `/api/prototypes/${prototypeId}/generations/${generationId}`
  );
  return toGenerationRun(response);
}
