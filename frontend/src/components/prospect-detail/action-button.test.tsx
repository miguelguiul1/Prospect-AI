import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActionButton } from "@/components/prospect-detail/action-button";
import type { ActionState } from "@/app/prospects/[companyId]/action-types";

describe("ActionButton", () => {
  it("shows a success message after the action resolves — never a silent no-op", async () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ status: "success", message: "Auditoria executada." }));
    render(<ActionButton action={action} companyId="c1" label="Rodar auditoria" pendingLabel="Auditando…" />);

    await userEvent.click(screen.getByRole("button", { name: "Rodar auditoria" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Auditoria executada."));
    expect(action).toHaveBeenCalledOnce();
  });

  it("shows the real error message on failure — never a generic success", async () => {
    const action = vi.fn(
      async (): Promise<ActionState> => ({ status: "error", message: "Company não encontrada." })
    );
    render(<ActionButton action={action} companyId="c1" label="Calcular score" pendingLabel="Calculando…" />);

    await userEvent.click(screen.getByRole("button", { name: "Calcular score" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Company não encontrada."));
  });

  it("passes the companyId through as a hidden field", () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ status: "idle" }));
    const { container } = render(
      <ActionButton action={action} companyId="company-xyz" label="X" pendingLabel="…" />
    );
    const hidden = container.querySelector('input[name="companyId"]') as HTMLInputElement;
    expect(hidden.value).toBe("company-xyz");
  });
});
