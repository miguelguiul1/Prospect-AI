import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ComponentPalette } from "@/components/prototype-builder/component-palette";
import { createInitialState } from "@/components/prototype-builder/builder-reducer";
import type { ComponentNode } from "@/lib/prototype/types";

function node(overrides: Partial<ComponentNode>): ComponentNode {
  return { id: "n1", type: "text", parentId: null, order: 0, props: {}, styles: {}, ...overrides };
}

describe("ComponentPalette", () => {
  it("lists every catalog component grouped by category", () => {
    render(<ComponentPalette state={createInitialState([])} dispatch={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Button" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Container" })).toBeInTheDocument();
    expect(screen.getByText("Layout")).toBeInTheDocument();
    expect(screen.getByText("Formulário")).toBeInTheDocument();
  });

  it("adds a component at the root when nothing is selected", async () => {
    const dispatch = vi.fn();
    render(<ComponentPalette state={createInitialState([])} dispatch={dispatch} />);

    await userEvent.click(screen.getByRole("button", { name: "Button" }));

    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "ADD_COMPONENT", componentType: "button", parentId: null })
    );
  });

  it("adds inside the selected container, never inside a leaf component", async () => {
    const dispatch = vi.fn();
    const container = node({ id: "root", type: "container" });
    const state = { ...createInitialState([container]), selectedId: "root" };
    render(<ComponentPalette state={state} dispatch={dispatch} />);

    await userEvent.click(screen.getByRole("button", { name: "Text" }));

    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ parentId: "root" }));
  });

  it("falls back to the root when the selected component cannot accept children", async () => {
    const dispatch = vi.fn();
    const leaf = node({ id: "leaf", type: "text" });
    const state = { ...createInitialState([leaf]), selectedId: "leaf" };
    render(<ComponentPalette state={state} dispatch={dispatch} />);

    await userEvent.click(screen.getByRole("button", { name: "Heading" }));

    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ parentId: null }));
  });
});
