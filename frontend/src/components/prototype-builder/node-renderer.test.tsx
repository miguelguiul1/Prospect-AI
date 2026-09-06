import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { NodeLeafContent } from "@/components/prototype-builder/node-renderer";
import type { ComponentNode } from "@/lib/prototype/types";

function node(overrides: Partial<ComponentNode>): ComponentNode {
  return { id: "n1", type: "text", parentId: null, order: 0, props: {}, styles: {}, ...overrides };
}

describe("NodeLeafContent — security", () => {
  it("renders user text as plain text, never as HTML", () => {
    const malicious = "<img src=x onerror=alert(1)>";
    render(<NodeLeafContent node={node({ type: "text", props: { content: malicious } })} />);

    // O texto aparece literalmente na página — não foi interpretado como HTML,
    // e nenhum elemento <img> extra foi criado a partir dele.
    expect(screen.getByText(malicious)).toBeInTheDocument();
    expect(document.querySelectorAll("img")).toHaveLength(0);
  });

  it("refuses a javascript: URL as an image source", () => {
    render(<NodeLeafContent node={node({ type: "image", props: { src: "javascript:alert(1)" } })} />);
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("Sem imagem")).toBeInTheDocument();
  });

  it("refuses a data:text/html URL as an image source", () => {
    render(<NodeLeafContent node={node({ type: "image", props: { src: "data:text/html,<script>alert(1)</script>" } })} />);
    expect(document.querySelector("img")).toBeNull();
  });

  it("accepts a plain https image URL", () => {
    render(<NodeLeafContent node={node({ type: "image", props: { src: "https://example.com/logo.png", alt: "Logo" } })} />);
    const img = document.querySelector("img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("src")).toBe("https://example.com/logo.png");
  });

  it("never renders raw HTML for a button's label", () => {
    render(<NodeLeafContent node={node({ type: "button", props: { content: "<b>bold</b>" } })} />);
    expect(screen.getByText("<b>bold</b>")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
  });
});

describe("NodeLeafContent — rendering", () => {
  it("renders a heading with its content", () => {
    render(<NodeLeafContent node={node({ type: "heading", props: { content: "Título" } })} />);
    expect(screen.getByRole("heading", { name: "Título" })).toBeInTheDocument();
  });

  it("renders a disabled input with its placeholder", () => {
    render(<NodeLeafContent node={node({ type: "input", props: { placeholder: "Digite seu nome" } })} />);
    expect(screen.getByPlaceholderText("Digite seu nome")).toBeDisabled();
  });

  it("falls back to a default label when content is missing", () => {
    render(<NodeLeafContent node={node({ type: "text", props: {} })} />);
    expect(screen.getByText("Texto de exemplo")).toBeInTheDocument();
  });

  it("renders a divider as an hr", () => {
    render(<NodeLeafContent node={node({ type: "divider" })} />);
    expect(document.querySelector("hr")).not.toBeNull();
  });
});
