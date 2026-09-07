import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ContactSummary } from "@/lib/api/types";

const createContactAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "success", message: "Contato adicionado." }));
vi.mock("@/app/crm/actions", () => ({
  createContactAction: (...args: Parameters<typeof createContactAction>) => createContactAction(...args),
}));

const { ContactsPanel } = await import("@/components/crm/contacts-panel");

function contact(overrides: Partial<ContactSummary> = {}): ContactSummary {
  return { id: "c1", name: "Maria Silva", role: "Sócia", email: null, phone: null, validation_status: "unverified", ...overrides };
}

describe("ContactsPanel", () => {
  it("shows an empty-state message with no contacts", () => {
    render(<ContactsPanel opportunityId="o1" companyId="comp1" contacts={[]} />);
    expect(screen.getByText(/nenhum contato cadastrado/i)).toBeInTheDocument();
  });

  it("lists a contact's name", () => {
    render(<ContactsPanel opportunityId="o1" companyId="comp1" contacts={[contact()]} />);
    expect(screen.getByText("Maria Silva")).toBeInTheDocument();
  });

  it("marks an unverified contact distinctly from a verified one", () => {
    render(
      <ContactsPanel
        opportunityId="o1"
        companyId="comp1"
        contacts={[contact({ id: "c1", name: "Não validada" }), contact({ id: "c2", name: "Validada", validation_status: "verified" })]}
      />
    );
    expect(screen.getByText("Não validado")).toBeInTheDocument();
    expect(screen.getByText("Validado")).toBeInTheDocument();
  });

  it("opens a dialog with a required name field when adding a contact", async () => {
    render(<ContactsPanel opportunityId="o1" companyId="comp1" contacts={[]} />);
    await userEvent.click(screen.getByRole("button", { name: /contato/i }));
    expect(screen.getByLabelText(/nome/i)).toBeRequired();
  });
});
