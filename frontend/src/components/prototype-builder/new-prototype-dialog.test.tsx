import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/app/prototypes/actions", () => ({
  createPrototypeAction: vi.fn(async () => ({ status: "error", message: "Informe um nome para o protótipo." })),
}));

const { NewPrototypeDialog } = await import("@/components/prototype-builder/new-prototype-dialog");

describe("NewPrototypeDialog", () => {
  it("opens the dialog with name and description fields", async () => {
    render(<NewPrototypeDialog />);
    await userEvent.click(screen.getByRole("button", { name: /novo protótipo/i }));

    expect(screen.getByLabelText(/nome/i)).toBeRequired();
    expect(screen.getByLabelText(/descrição/i)).toBeInTheDocument();
  });

  it("requires a name before the form can be submitted", async () => {
    render(<NewPrototypeDialog />);
    await userEvent.click(screen.getByRole("button", { name: /novo protótipo/i }));

    const nameField = screen.getByLabelText(/nome/i) as HTMLInputElement;
    expect(nameField.required).toBe(true);
    expect(nameField.value).toBe("");
  });
});
