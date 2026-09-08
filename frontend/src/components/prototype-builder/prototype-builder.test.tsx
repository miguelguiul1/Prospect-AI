import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const savePrototypeAction = vi.fn(async (_id: string, _input: { name: string; components: unknown[] }) => ({
  status: "success" as const,
  updatedAt: "2026-09-06T12:00:00Z",
}));

vi.mock("@/app/prototypes/[prototypeId]/actions", () => ({
  savePrototypeAction: (id: string, input: { name: string; components: unknown[] }) => savePrototypeAction(id, input),
  // Nenhum teste aqui aciona o refinamento (ver refinement-bar.test.tsx
  // para isso isoladamente) — só evita um import undefined quando
  // `RefinementBar` (renderizado dentro de `PrototypeBuilder`) resolve o
  // módulo mockado.
  refinePrototypeAction: vi.fn(),
}));

const { PrototypeBuilder } = await import("@/components/prototype-builder/prototype-builder");

describe("PrototypeBuilder", () => {
  it("starts with the save button disabled — nothing to save yet", () => {
    render(<PrototypeBuilder prototypeId="p1" initialName="Meu protótipo" initialComponents={[]} />);
    expect(screen.getByRole("button", { name: /^salvar$/i })).toBeDisabled();
  });

  it("adding a component enables Save and selects it for editing", async () => {
    render(<PrototypeBuilder prototypeId="p1" initialName="Meu protótipo" initialComponents={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Heading" }));

    expect(screen.getByRole("button", { name: /^salvar$/i })).toBeEnabled();
    expect(screen.getByLabelText("Conteúdo")).toBeInTheDocument(); // painel de propriedades do Heading
    expect(screen.getByText("1 componente")).toBeInTheDocument();
  });

  it("saving calls the server action with the current name and tree, then clears dirty state", async () => {
    render(<PrototypeBuilder prototypeId="proto-123" initialName="Original" initialComponents={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Button" }));
    await userEvent.click(screen.getByRole("button", { name: /^salvar$/i }));

    await waitFor(() => expect(savePrototypeAction).toHaveBeenCalledOnce());
    const [id, payload] = savePrototypeAction.mock.calls[0];
    expect(id).toBe("proto-123");
    expect(payload.name).toBe("Original");
    expect(payload.components).toHaveLength(1);

    await waitFor(() => expect(screen.getByRole("button", { name: /^salvar$/i })).toBeDisabled());
  });

  it("toggling preview hides the component palette and property panel", async () => {
    render(<PrototypeBuilder prototypeId="p1" initialName="X" initialComponents={[]} />);

    expect(screen.getByTestId("component-palette")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /preview/i }));

    expect(screen.queryByTestId("component-palette")).not.toBeInTheDocument();
    expect(screen.queryByTestId("property-panel")).not.toBeInTheDocument();
  });

  it("shows the real error from a failed save instead of pretending it worked", async () => {
    savePrototypeAction.mockResolvedValueOnce({ status: "error", message: "Prototype não encontrado." } as never);
    render(<PrototypeBuilder prototypeId="p1" initialName="X" initialComponents={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Card" }));
    await userEvent.click(screen.getByRole("button", { name: /^salvar$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Prototype não encontrado.");
  });
});
