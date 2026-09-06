import {
  Square,
  Rows3,
  Columns3,
  LayoutPanelLeft,
  Heading as HeadingIcon,
  MousePointerClick,
  Image as ImageIcon,
  TextCursorInput,
  AlignLeft,
  CreditCard,
  Minus,
  type LucideIcon,
} from "lucide-react";
import type { ComponentType, PrimitiveValue } from "@/lib/prototype/types";

export interface PropertyField {
  key: string;
  scope: "props" | "styles";
  label: string;
  kind: "text" | "textarea" | "select" | "number" | "color";
  options?: { label: string; value: string }[];
}

export interface ComponentDefinition {
  type: ComponentType;
  label: string;
  category: "layout" | "content" | "form" | "interface";
  icon: LucideIcon;
  /** Aceita componentes filhos no Canvas (arrastados/adicionados dentro dele). */
  acceptsChildren: boolean;
  fields: PropertyField[];
  defaultProps: Record<string, PrimitiveValue>;
  defaultStyles: Record<string, PrimitiveValue>;
}

const ALIGN_OPTIONS = [
  { label: "Esquerda", value: "left" },
  { label: "Centro", value: "center" },
  { label: "Direita", value: "right" },
];

const WEIGHT_OPTIONS = [
  { label: "Normal", value: "400" },
  { label: "Média", value: "500" },
  { label: "Negrito", value: "700" },
];

const BUTTON_VARIANT_OPTIONS = [
  { label: "Primário", value: "primary" },
  { label: "Secundário", value: "secondary" },
  { label: "Contorno", value: "outline" },
];

/**
 * Catálogo de componentes iniciais do Prototype Builder (seção 4 do
 * Prompt 09) — pequeno de propósito. `type` aqui deve corresponder
 * exatamente a `COMPONENT_TYPES` do backend
 * (`backend/app/domains/prototypes/schemas.py`): o backend é sempre a
 * autoridade de validação real, este registro só descreve como cada tipo
 * é exibido/editado no Builder.
 */
export const COMPONENT_REGISTRY: Record<ComponentType, ComponentDefinition> = {
  container: {
    type: "container", label: "Container", category: "layout", icon: Square, acceptsChildren: true,
    fields: [{ key: "padding", scope: "styles", label: "Espaçamento interno (px)", kind: "number" }],
    defaultProps: {}, defaultStyles: { padding: 16 },
  },
  section: {
    type: "section", label: "Section", category: "layout", icon: LayoutPanelLeft, acceptsChildren: true,
    fields: [{ key: "padding", scope: "styles", label: "Espaçamento interno (px)", kind: "number" }],
    defaultProps: {}, defaultStyles: { padding: 24 },
  },
  row: {
    type: "row", label: "Row", category: "layout", icon: Rows3, acceptsChildren: true,
    fields: [{ key: "gap", scope: "styles", label: "Espaço entre itens (px)", kind: "number" }],
    defaultProps: {}, defaultStyles: { gap: 12 },
  },
  column: {
    type: "column", label: "Column", category: "layout", icon: Columns3, acceptsChildren: true,
    fields: [{ key: "gap", scope: "styles", label: "Espaço entre itens (px)", kind: "number" }],
    defaultProps: {}, defaultStyles: { gap: 12 },
  },
  text: {
    type: "text", label: "Text", category: "content", icon: AlignLeft, acceptsChildren: false,
    fields: [
      { key: "content", scope: "props", label: "Conteúdo", kind: "textarea" },
      { key: "align", scope: "styles", label: "Alinhamento", kind: "select", options: ALIGN_OPTIONS },
      { key: "color", scope: "styles", label: "Cor", kind: "color" },
    ],
    defaultProps: { content: "Texto de exemplo" }, defaultStyles: { align: "left" },
  },
  heading: {
    type: "heading", label: "Heading", category: "content", icon: HeadingIcon, acceptsChildren: false,
    fields: [
      { key: "content", scope: "props", label: "Conteúdo", kind: "text" },
      { key: "align", scope: "styles", label: "Alinhamento", kind: "select", options: ALIGN_OPTIONS },
      { key: "weight", scope: "styles", label: "Peso", kind: "select", options: WEIGHT_OPTIONS },
    ],
    defaultProps: { content: "Título" }, defaultStyles: { align: "left", weight: "700" },
  },
  button: {
    type: "button", label: "Button", category: "content", icon: MousePointerClick, acceptsChildren: false,
    fields: [
      { key: "content", scope: "props", label: "Texto", kind: "text" },
      { key: "variant", scope: "props", label: "Variante", kind: "select", options: BUTTON_VARIANT_OPTIONS },
    ],
    defaultProps: { content: "Clique aqui", variant: "primary" }, defaultStyles: {},
  },
  image: {
    type: "image", label: "Image", category: "content", icon: ImageIcon, acceptsChildren: false,
    fields: [
      { key: "src", scope: "props", label: "URL", kind: "text" },
      { key: "alt", scope: "props", label: "Texto alternativo", kind: "text" },
      { key: "width", scope: "styles", label: "Largura (px)", kind: "number" },
      { key: "height", scope: "styles", label: "Altura (px)", kind: "number" },
    ],
    defaultProps: { src: "", alt: "" }, defaultStyles: { width: 240, height: 160 },
  },
  input: {
    type: "input", label: "Input", category: "form", icon: TextCursorInput, acceptsChildren: false,
    fields: [
      { key: "label", scope: "props", label: "Rótulo", kind: "text" },
      { key: "placeholder", scope: "props", label: "Placeholder", kind: "text" },
      {
        key: "inputType", scope: "props", label: "Tipo", kind: "select",
        options: [
          { label: "Texto", value: "text" }, { label: "E-mail", value: "email" }, { label: "Número", value: "number" },
        ],
      },
    ],
    defaultProps: { label: "Rótulo", placeholder: "Digite aqui...", inputType: "text" }, defaultStyles: {},
  },
  textarea: {
    type: "textarea", label: "Textarea", category: "form", icon: TextCursorInput, acceptsChildren: false,
    fields: [
      { key: "label", scope: "props", label: "Rótulo", kind: "text" },
      { key: "placeholder", scope: "props", label: "Placeholder", kind: "text" },
    ],
    defaultProps: { label: "Rótulo", placeholder: "Digite aqui..." }, defaultStyles: {},
  },
  card: {
    type: "card", label: "Card", category: "interface", icon: CreditCard, acceptsChildren: true,
    fields: [{ key: "padding", scope: "styles", label: "Espaçamento interno (px)", kind: "number" }],
    defaultProps: {}, defaultStyles: { padding: 16 },
  },
  divider: {
    type: "divider", label: "Divider", category: "interface", icon: Minus, acceptsChildren: false,
    fields: [], defaultProps: {}, defaultStyles: {},
  },
};

export const COMPONENT_LIST = Object.values(COMPONENT_REGISTRY);

export function definitionFor(type: string): ComponentDefinition | undefined {
  return COMPONENT_REGISTRY[type as ComponentType];
}
