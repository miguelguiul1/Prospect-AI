import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { OutreachMessage } from "@/lib/api/types";

const generateOutreachAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "error", message: "Não foi possível gerar a sugestão de outreach: sem chave configurada." }));
const editOutreachAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "success" }));
const transitionOutreachAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "success" }));
vi.mock("@/app/crm/actions", () => ({
  generateOutreachAction: (...args: Parameters<typeof generateOutreachAction>) => generateOutreachAction(...args),
  editOutreachAction: (...args: Parameters<typeof editOutreachAction>) => editOutreachAction(...args),
  transitionOutreachAction: (...args: Parameters<typeof transitionOutreachAction>) => transitionOutreachAction(...args),
}));

const { OutreachPanel } = await import("@/components/crm/outreach-panel");

function draft(overrides: Partial<OutreachMessage> = {}): OutreachMessage {
  return {
    id: "out1",
    opportunity_id: "o1",
    contact_id: null,
    channel: "email",
    status: "draft",
    subject: "Uma proposta rápida",
    message: "Olá, tudo bem?",
    rationale: "Site não confirmado como ativo.",
    evidence_ids: [],
    generated_by_ai: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("OutreachPanel", () => {
  it("shows an empty-state message with no history", () => {
    render(<OutreachPanel opportunityId="o1" contacts={[]} history={[]} />);
    expect(screen.getByText(/nenhuma sugestão gerada ainda/i)).toBeInTheDocument();
  });

  it("shows the real error message when generation fails — never a fabricated draft", async () => {
    render(<OutreachPanel opportunityId="o1" contacts={[]} history={[]} />);
    await userEvent.click(screen.getByRole("button", { name: /gerar sugestão/i }));
    await waitFor(() =>
      expect(screen.getByText(/não foi possível gerar a sugestão/i)).toBeInTheDocument()
    );
  });

  it("shows an editable subject/message for a draft, with a rationale", () => {
    render(<OutreachPanel opportunityId="o1" contacts={[]} history={[draft()]} />);
    expect(screen.getByDisplayValue("Uma proposta rápida")).toBeInTheDocument();
    expect(screen.getByText(/site não confirmado como ativo/i)).toBeInTheDocument();
  });

  it("offers mark-sent and cancel actions for a draft", () => {
    render(<OutreachPanel opportunityId="o1" contacts={[]} history={[draft()]} />);
    expect(screen.getByRole("button", { name: /já enviei manualmente/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancelar/i })).toBeInTheDocument();
  });

  it("a sent outreach shows plain text instead of an editable form", () => {
    render(<OutreachPanel opportunityId="o1" contacts={[]} history={[draft({ status: "sent_manually" })]} />);
    expect(screen.queryByDisplayValue("Uma proposta rápida")).not.toBeInTheDocument();
    expect(screen.getByText("Uma proposta rápida")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /já enviei manualmente/i })).not.toBeInTheDocument();
  });

  it("only offers verified contacts for personalization", () => {
    render(
      <OutreachPanel
        opportunityId="o1"
        contacts={[
          { id: "c1", name: "Não validado", role: null, email: null, phone: null, validation_status: "unverified" },
          { id: "c2", name: "Validado", role: null, email: null, phone: null, validation_status: "verified" },
        ]}
        history={[]}
      />
    );
    const select = screen.getByLabelText(/personalizar para/i) as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map((o) => o.textContent);
    expect(optionLabels).toContain("Validado");
    expect(optionLabels).not.toContain("Não validado");
  });
});
