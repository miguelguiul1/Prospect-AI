import "server-only";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api/client";
import type { ComponentNode } from "@/lib/prototype/types";

interface PrototypeSummaryResponse {
  id: string;
  name: string;
  description: string | null;
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

export async function createPrototype(input: { name: string; description?: string }): Promise<PrototypeDetail> {
  const response = await apiPost<PrototypeDetailResponse>("/api/prototypes", input);
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
