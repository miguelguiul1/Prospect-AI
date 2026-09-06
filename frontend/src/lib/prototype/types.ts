/**
 * Tipos do Prototype Builder — espelham `backend/app/domains/prototypes/
 * schemas.py`. `ComponentType` deve ser mantido em sincronia manual com
 * `COMPONENT_TYPES` do backend (o backend é sempre a autoridade real: um
 * `type` fora dali é rejeitado no `PUT`, não importa o que o frontend
 * mande — ver `docs/prototype-builder.md`).
 */

export type PrimitiveValue = string | number | boolean | null;

export const COMPONENT_TYPES = [
  "container",
  "section",
  "row",
  "column",
  "text",
  "heading",
  "button",
  "image",
  "input",
  "textarea",
  "card",
  "divider",
] as const;

export type ComponentType = (typeof COMPONENT_TYPES)[number];

export interface ComponentNode {
  id: string;
  type: ComponentType;
  parentId: string | null;
  order: number;
  props: Record<string, PrimitiveValue>;
  styles: Record<string, PrimitiveValue>;
}

export type BuilderMode = "edit" | "preview";

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
  settings: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}
