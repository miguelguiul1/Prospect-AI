import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const refinePrototypeAction = vi.fn();
vi.mock("@/app/prototypes/[prototypeId]/actions", () => ({
  refinePrototypeAction: (...args: unknown[]) => refinePrototypeAction(...args),
}));

const { RefinementBar } = await import("@/components/prototype-builder/refinement-bar");

describe("RefinementBar", () => {
  it("apply button is disabled with an empty instruction", () => {
    render(<RefinementBar prototypeId="p1" dispatch={vi.fn()} />);
    expect(screen.getByRole("button", { name: /aplicar/i })).toBeDisabled();
  });

  it("submitting a successful refinement dispatches LOAD with the new components", async () => {
    const newComponents = [{ id: "a", type: "heading", parentId: null, order: 0, props: {}, styles: {} }];
    refinePrototypeAction.mockResolvedValueOnce({ status: "success", components: newComponents, run: { groundingWarnings: null } });
    const dispatch = vi.fn();
    render(<RefinementBar prototypeId="p1" dispatch={dispatch} />);

    await userEvent.type(screen.getByLabelText(/instrução de refinamento/i), "deixa mais premium");
    await userEvent.click(screen.getByRole("button", { name: /aplicar/i }));

    await waitFor(() => expect(dispatch).toHaveBeenCalledWith({ type: "LOAD", components: newComponents }));
    expect(refinePrototypeAction).toHaveBeenCalledWith("p1", "deixa mais premium");
  });

  it("a failed refinement shows the error message and never dispatches LOAD", async () => {
    refinePrototypeAction.mockResolvedValueOnce({ status: "error", message: "Limite diário atingido." });
    const dispatch = vi.fn();
    render(<RefinementBar prototypeId="p1" dispatch={dispatch} />);

    await userEvent.type(screen.getByLabelText(/instrução de refinamento/i), "muda algo");
    await userEvent.click(screen.getByRole("button", { name: /aplicar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Limite diário atingido.");
    expect(dispatch).not.toHaveBeenCalled();
  });

  it("shows grounding warnings returned from a successful refinement", async () => {
    refinePrototypeAction.mockResolvedValueOnce({
      status: "success",
      components: [],
      run: { groundingWarnings: ["componente 'x' contém algo que parece telefone"] },
    });
    render(<RefinementBar prototypeId="p1" dispatch={vi.fn()} />);

    await userEvent.type(screen.getByLabelText(/instrução de refinamento/i), "adiciona um telefone");
    await userEvent.click(screen.getByRole("button", { name: /aplicar/i }));

    expect(await screen.findByText(/parece telefone/i)).toBeInTheDocument();
  });
});
