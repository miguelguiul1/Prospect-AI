import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Canvas } from "@/components/prototype-builder/canvas";
import { createInitialState } from "@/components/prototype-builder/builder-reducer";
import type { ComponentNode } from "@/lib/prototype/types";

function node(overrides: Partial<ComponentNode>): ComponentNode {
  return { id: "n1", type: "text", parentId: null, order: 0, props: {}, styles: {}, ...overrides };
}

describe("Canvas", () => {
  it("shows an empty state when there are no components", () => {
    render(<Canvas state={createInitialState([])} dispatch={vi.fn()} />);
    expect(screen.getByText(/o canvas está vazio/i)).toBeInTheDocument();
  });

  it("selects a component when clicked", async () => {
    const dispatch = vi.fn();
    const state = createInitialState([node({ id: "a", type: "button", props: { content: "Clique" } })]);
    render(<Canvas state={state} dispatch={dispatch} />);

    await userEvent.click(screen.getByText("Clique"));

    expect(dispatch).toHaveBeenCalledWith({ type: "SELECT", id: "a" });
  });

  it("clicking the empty canvas background deselects", async () => {
    const dispatch = vi.fn();
    const state = createInitialState([node({ id: "a" })]);
    const { container } = render(<Canvas state={state} dispatch={dispatch} />);

    await userEvent.click(container.querySelector('[data-testid="canvas"]')!);

    expect(dispatch).toHaveBeenCalledWith({ type: "SELECT", id: null });
  });

  it("renders nested children inside a container", () => {
    const state = createInitialState([
      node({ id: "root", type: "container" }),
      node({ id: "child", type: "heading", parentId: "root", props: { content: "Dentro" } }),
    ]);
    render(<Canvas state={state} dispatch={vi.fn()} />);
    expect(screen.getByText("Dentro")).toBeInTheDocument();
  });

  it("renders no selection outline chrome in preview mode", () => {
    const state = { ...createInitialState([node({ id: "a" })]), mode: "preview" as const };
    render(<Canvas state={state} dispatch={vi.fn()} />);
    // Em preview, o texto ainda aparece, mas sem o rótulo de seleção do editor.
    expect(screen.queryByRole("button", { name: /selecionar componente/i })).not.toBeInTheDocument();
  });
});
