import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mesma razão de sales-brief-section.test.tsx: `actions.ts` importa
// transitivamente `lib/api/*` (pacote `server-only`) — sempre mockado em
// teste de componente.
vi.mock("@/app/prospects/[companyId]/actions", () => ({
  generatePrototypeAction: vi.fn(),
}));

const { PrototypeSection } = await import("@/components/prospect-detail/prototype-section");

describe("PrototypeSection", () => {
  it("requires an Opportunity before offering to generate a prototype", () => {
    render(<PrototypeSection companyId="c1" hasOpportunity={false} />);
    expect(screen.getByText(/crie uma oportunidade/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /gerar protótipo/i })).not.toBeInTheDocument();
  });

  it("shows the generate button once an Opportunity exists", () => {
    render(<PrototypeSection companyId="c1" hasOpportunity />);
    expect(screen.getByRole("button", { name: /gerar protótipo/i })).toBeInTheDocument();
  });
});
