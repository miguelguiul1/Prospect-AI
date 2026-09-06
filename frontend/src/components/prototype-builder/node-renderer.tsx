import type { CSSProperties } from "react";
import type { ComponentNode } from "@/lib/prototype/types";

/**
 * Renderiza o CONTEÚDO de um nó (sem os filhos — isso é responsabilidade
 * de quem chama, recursivamente, tanto no Canvas quanto no Preview: ver
 * `docs/prototype-builder.md`, "por que Canvas e Preview usam o mesmo
 * renderer"). Nunca usa `dangerouslySetInnerHTML` — todo texto do usuário
 * (`props.content`, `props.label`, ...) é sempre filho de texto comum do
 * React, que escapa automaticamente. Isso é o que torna impossível usar um
 * protótipo para injetar HTML/JavaScript arbitrário (seção 10 do Prompt 09).
 */

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function num(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

/** Bloqueia esquemas de URL perigosos (`javascript:`, `data:text/html`) em
 * `<img src>` — defesa em profundidade, mesmo o React já escapando o
 * atributo. Aceita apenas http(s) e caminhos relativos. */
function isSafeImageSrc(src: string): boolean {
  if (!src) return false;
  if (src.startsWith("/") || src.startsWith("./")) return true;
  try {
    const url = new URL(src);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function stylesOf(node: ComponentNode): CSSProperties {
  const s = node.styles;
  const style: CSSProperties = {};
  if (typeof s.padding === "number") style.padding = s.padding;
  if (typeof s.gap === "number") style.gap = s.gap;
  if (typeof s.width === "number") style.width = s.width;
  if (typeof s.height === "number") style.height = s.height;
  if (typeof s.align === "string") style.textAlign = s.align as CSSProperties["textAlign"];
  if (typeof s.weight === "string") style.fontWeight = s.weight;
  if (typeof s.color === "string") style.color = s.color;
  return style;
}

const BUTTON_VARIANT_CLASS: Record<string, string> = {
  primary: "bg-primary text-primary-foreground",
  secondary: "bg-secondary text-secondary-foreground",
  outline: "border border-border bg-transparent text-foreground",
};

export function NodeLeafContent({ node }: { node: ComponentNode }) {
  const style = stylesOf(node);

  switch (node.type) {
    case "text":
      return <p style={style}>{str(node.props.content, "Texto de exemplo")}</p>;

    case "heading":
      return (
        <h3 style={style} className="text-xl">
          {str(node.props.content, "Título")}
        </h3>
      );

    case "button":
      return (
        <span
          role="button"
          className={`inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium ${
            BUTTON_VARIANT_CLASS[str(node.props.variant, "primary")] ?? BUTTON_VARIANT_CLASS.primary
          }`}
        >
          {str(node.props.content, "Clique aqui")}
        </span>
      );

    case "image": {
      const src = str(node.props.src);
      const width = num(node.styles.width) ?? 240;
      const height = num(node.styles.height) ?? 160;
      if (!isSafeImageSrc(src)) {
        return (
          <div
            style={{ width, height }}
            className="flex items-center justify-center rounded-md border border-dashed border-border bg-muted text-xs text-muted-foreground"
          >
            Sem imagem
          </div>
        );
      }
      // eslint-disable-next-line @next/next/no-img-element -- URL do usuário, não um asset local otimizável
      return <img src={src} alt={str(node.props.alt)} width={width} height={height} className="rounded-md object-cover" />;
    }

    case "input":
      return (
        <label className="flex flex-col gap-1 text-sm">
          {str(node.props.label) && <span className="text-foreground">{str(node.props.label)}</span>}
          <input
            type={str(node.props.inputType, "text")}
            placeholder={str(node.props.placeholder)}
            disabled
            className="rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
          />
        </label>
      );

    case "textarea":
      return (
        <label className="flex flex-col gap-1 text-sm">
          {str(node.props.label) && <span className="text-foreground">{str(node.props.label)}</span>}
          <textarea
            placeholder={str(node.props.placeholder)}
            disabled
            rows={3}
            className="rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
          />
        </label>
      );

    case "divider":
      return <hr className="border-border" />;

    default:
      return null;
  }
}

export function containerClassName(type: string): string {
  switch (type) {
    case "row":
      return "flex flex-row flex-wrap";
    case "column":
      return "flex flex-col";
    case "card":
      return "rounded-lg border border-border bg-card shadow-sm";
    case "section":
      return "w-full";
    default:
      return "";
  }
}

export function containerStyle(node: ComponentNode): CSSProperties {
  return stylesOf(node);
}
