import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// `actions.ts` transitivamente importa `lib/api/*`, que usam o pacote
// `server-only` — inerte fora do bundler do Next.js, então é sempre
// mockado em teste de componente (a Server Action real é validada pelos
// testes de backend + validação manual, nunca aqui).
vi.mock("@/app/prospects/[companyId]/actions", () => ({
  generateBriefAction: vi.fn(),
}));

const { SalesBriefSection } = await import("@/components/prospect-detail/sales-brief-section");

describe("SalesBriefSection", () => {
  it("requires an Opportunity Score before offering to generate a brief", () => {
    render(<SalesBriefSection companyId="c1" brief={null} hasScore={false} />);
    expect(screen.getByText(/calcule o opportunity score antes/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /gerar sales brief/i })).not.toBeInTheDocument();
  });

  it("shows a CTA to generate when no brief exists yet — never a fake one", () => {
    render(<SalesBriefSection companyId="c1" brief={null} hasScore />);
    expect(screen.getByText(/sales brief ainda não gerado/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /gerar sales brief/i })).toBeInTheDocument();
  });

  it("shows the real provider error when generation failed — never masks it as success", () => {
    render(
      <SalesBriefSection
        companyId="c1"
        hasScore
        brief={{
          id: "b1",
          status: "failed",
          content: null,
          provider: "anthropic",
          model: null,
          error_code: "ProviderUnavailableError",
          error_message: "ANTHROPIC_API_KEY não configurada.",
          generated_at: "2026-09-06T10:00:00Z",
        }}
      />
    );
    expect(screen.getByText("ANTHROPIC_API_KEY não configurada.")).toBeInTheDocument();
  });

  it("renders the full structured content when the brief succeeded", () => {
    render(
      <SalesBriefSection
        companyId="c1"
        hasScore
        brief={{
          id: "b1",
          status: "completed",
          provider: "anthropic",
          model: "claude-x",
          error_code: null,
          error_message: null,
          generated_at: "2026-09-06T10:00:00Z",
          content: {
            summary: "Resumo do prospect.",
            opportunity: "Boa oportunidade.",
            why_this_prospect: "Motivo.",
            digital_gaps: "Sem site.",
            suggested_angle: "Ângulo.",
            talking_points: ["Ponto 1", "Ponto 2", "Ponto 3"],
            risks_and_caveats: "Ressalva.",
            evidence_used: ["site_state: not_detected"],
          },
        }}
      />
    );
    expect(screen.getByText("Resumo do prospect.")).toBeInTheDocument();
    expect(screen.getByText("Ponto 1")).toBeInTheDocument();
    expect(screen.getByText("site_state: not_detected")).toBeInTheDocument();
  });
});
