import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PropertyPanel } from "@/components/prototype-builder/property-panel";
import { createInitialState } from "@/components/prototype-builder/builder-reducer";
import type { ComponentNode } from "@/lib/prototype/types";

function node(overrides: Partial<ComponentNode>): ComponentNode {
  return { id: "n1", type: "text", parentId: null, order: 0, props: {}, styles: {}, ...overrides };
}

describe("PropertyPanel", () => {
  it("shows a placeholder when nothing is selected", () => {
    render(<PropertyPanel state={createInitialState([node({ id: "a" })])} dispatch={vi.fn()} />);
    expect(screen.getByText(/nenhum componente selecionado/i)).toBeInTheDocument();
  });

  it("shows the fields for the selected component's type", () => {
    const state = { ...createInitialState([node({ id: "a", type: "heading" })]), selectedId: "a" };
    render(<PropertyPanel state={state} dispatch={vi.fn()} />);

    expect(screen.getByLabelText("Conteúdo")).toBeInTheDocument();
    expect(screen.getByLabelText("Alinhamento")).toBeInTheDocument();
  });

  it("dispatches UPDATE_PROP with the correct scope when a field changes", async () => {
    const dispatch = vi.fn();
    const state = { ...createInitialState([node({ id: "a", type: "text", props: { content: "" } })]), selectedId: "a" };
    render(<PropertyPanel state={state} dispatch={dispatch} />);

    await userEvent.type(screen.getByLabelText("Conteúdo"), "x");

    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "UPDATE_PROP", id: "a", scope: "props", key: "content" })
    );
  });

  it("dispatches REMOVE_SELECTED when the delete button is clicked", async () => {
    const dispatch = vi.fn();
    const state = { ...createInitialState([node({ id: "a" })]), selectedId: "a" };
    render(<PropertyPanel state={state} dispatch={dispatch} />);

    await userEvent.click(screen.getByRole("button", { name: /remover componente/i }));

    expect(dispatch).toHaveBeenCalledWith({ type: "REMOVE_SELECTED" });
  });

  it("shows a message for components with no editable properties", () => {
    const state = { ...createInitialState([node({ id: "a", type: "divider" })]), selectedId: "a" };
    render(<PropertyPanel state={state} dispatch={vi.fn()} />);
    expect(screen.getByText(/não tem propriedades editáveis/i)).toBeInTheDocument();
  });
});
