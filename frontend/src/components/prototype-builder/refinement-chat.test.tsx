import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { RefinementMessage } from "@/lib/api/prototypes";

const refinePrototypeAction = vi.fn();
vi.mock("@/app/prototypes/[prototypeId]/actions", () => ({
  refinePrototypeAction: (...args: unknown[]) => refinePrototypeAction(...args),
}));

const { RefinementChat } = await import("@/components/prototype-builder/refinement-chat");

function message(overrides: Partial<RefinementMessage> = {}): RefinementMessage {
  return {
    id: "r1",
    instruction: "deixa mais premium",
    status: "succeeded",
    errorMessage: null,
    groundingWarnings: null,
    diffSummary: null,
    versionId: "v2",
    versionNumber: 2,
    createdAt: "2026-09-08T12:00:00Z",
    ...overrides,
  };
}

describe("RefinementChat", () => {
  it("shows a hint instead of a message list when there is no history yet", () => {
    render(<RefinementChat prototypeId="p1" dispatch={vi.fn()} initialRefinements={[]} />);
    expect(screen.getByText(/peça uma mudança em linguagem natural/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/histórico de refinamento/i)).not.toBeInTheDocument();
  });

  it("renders past refinements from the initial history, oldest first", () => {
    const history = [
      message({ id: "r1", instruction: "primeiro pedido" }),
      message({ id: "r2", instruction: "segundo pedido", versionNumber: 3 }),
    ];
    render(<RefinementChat prototypeId="p1" dispatch={vi.fn()} initialRefinements={history} />);

    const items = screen.getAllByText(/pedido$/);
    expect(items.map((el) => el.textContent)).toEqual(["primeiro pedido", "segundo pedido"]);
  });

  it("a failed past refinement shows its error, never a version link", () => {
    const history = [
      message({ status: "failed", errorMessage: "Limite diário atingido.", versionId: null, versionNumber: null }),
    ];
    render(<RefinementChat prototypeId="p1" dispatch={vi.fn()} initialRefinements={history} />);

    expect(screen.getByText("Limite diário atingido.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /ver/i })).not.toBeInTheDocument();
  });

  it("a successful past refinement links to its resulting version", () => {
    render(<RefinementChat prototypeId="proto-1" dispatch={vi.fn()} initialRefinements={[message()]} />);

    const link = screen.getByRole("link", { name: /ver/i });
    expect(link).toHaveAttribute("href", "/prototypes/proto-1/versions/v2");
  });

  it("apply button is disabled with an empty instruction", () => {
    render(<RefinementChat prototypeId="p1" dispatch={vi.fn()} initialRefinements={[]} />);
    expect(screen.getByRole("button", { name: /aplicar/i })).toBeDisabled();
  });

  it("submitting a successful refinement dispatches LOAD and appends the fresh history", async () => {
    const newComponents = [{ id: "a", type: "heading", parentId: null, order: 0, props: {}, styles: {} }];
    const freshHistory = [message({ id: "r-new", instruction: "muda a cor do botão" })];
    refinePrototypeAction.mockResolvedValueOnce({ status: "ok", refinements: freshHistory, components: newComponents });
    const dispatch = vi.fn();
    render(<RefinementChat prototypeId="p1" dispatch={dispatch} initialRefinements={[]} />);

    await userEvent.type(screen.getByLabelText(/instrução de refinamento/i), "muda a cor do botão");
    await userEvent.click(screen.getByRole("button", { name: /aplicar/i }));

    await waitFor(() => expect(dispatch).toHaveBeenCalledWith({ type: "LOAD", components: newComponents }));
    expect(refinePrototypeAction).toHaveBeenCalledWith("p1", "muda a cor do botão");
    expect(screen.getByText("muda a cor do botão")).toBeInTheDocument();
  });

  it("a business failure (refinement itself failed) never dispatches LOAD but still shows the message", async () => {
    const freshHistory = [message({ status: "failed", errorMessage: "Conteúdo inseguro.", versionId: null, versionNumber: null })];
    refinePrototypeAction.mockResolvedValueOnce({ status: "ok", refinements: freshHistory });
    const dispatch = vi.fn();
    render(<RefinementChat prototypeId="p1" dispatch={dispatch} initialRefinements={[]} />);

    await userEvent.type(screen.getByLabelText(/instrução de refinamento/i), "pedido ruim");
    await userEvent.click(screen.getByRole("button", { name: /aplicar/i }));

    expect(await screen.findByText("Conteúdo inseguro.")).toBeInTheDocument();
    expect(dispatch).not.toHaveBeenCalled();
  });

  it("an exceptional error (network/API) shows a banner, not a chat message", async () => {
    refinePrototypeAction.mockResolvedValueOnce({ status: "error", message: "Sua sessão expirou." });
    render(<RefinementChat prototypeId="p1" dispatch={vi.fn()} initialRefinements={[]} />);

    await userEvent.type(screen.getByLabelText(/instrução de refinamento/i), "x");
    await userEvent.click(screen.getByRole("button", { name: /aplicar/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Sua sessão expirou.");
  });

  it("shows grounding warnings for the corresponding message", () => {
    const history = [message({ groundingWarnings: ["componente 'x' contém algo que parece telefone"] })];
    render(<RefinementChat prototypeId="p1" dispatch={vi.fn()} initialRefinements={history} />);

    expect(screen.getByText(/parece telefone/i)).toBeInTheDocument();
  });
});
