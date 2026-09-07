import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthForm } from "@/components/auth/auth-form";
import type { ActionState } from "@/lib/action-types";

describe("AuthForm", () => {
  it("login mode shows only email and password fields", () => {
    render(<AuthForm mode="login" action={vi.fn(async () => ({ status: "idle" }) as ActionState)} />);
    expect(screen.getByLabelText(/e-mail/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/senha/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^nome$/i)).not.toBeInTheDocument();
  });

  it("register mode also shows a name field", () => {
    render(<AuthForm mode="register" action={vi.fn(async () => ({ status: "idle" }) as ActionState)} />);
    expect(screen.getByLabelText(/^nome$/i)).toBeInTheDocument();
  });

  it("shows the real error message from the action — never a generic fallback", async () => {
    const action = vi.fn(async (): Promise<ActionState> => ({ status: "error", message: "E-mail ou senha inválidos." }));
    render(<AuthForm mode="login" action={action} />);

    await userEvent.type(screen.getByLabelText(/e-mail/i), "a@b.com");
    await userEvent.type(screen.getByLabelText(/senha/i), "senhaerrada123");
    await userEvent.click(screen.getByRole("button", { name: /entrar/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("E-mail ou senha inválidos."));
  });

  it("passes the next path through as a hidden field when provided", () => {
    const { container } = render(
      <AuthForm mode="login" action={vi.fn(async () => ({ status: "idle" }) as ActionState)} nextPath="/crm/pipeline" />
    );
    const hidden = container.querySelector('input[name="next"]') as HTMLInputElement;
    expect(hidden.value).toBe("/crm/pipeline");
  });
});
