import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OpportunitiesList } from "@/components/crm/opportunities-list";
import type { OpportunitySummary } from "@/lib/api/types";

function item(overrides: Partial<OpportunitySummary> = {}): OpportunitySummary {
  return {
    id: "o1",
    company_id: "c1",
    company_name: "Barbearia Central",
    category_name: "Barbearia",
    region_name: "São Paulo, SP",
    owner_id: "u1",
    owner_name: "Vendedora",
    stage: { id: "s1", key: "new", name: "Novo", order: 1, is_won: false, is_lost: false },
    status: "open",
    priority: "medium",
    opportunity_score: 72.5,
    opportunity_tier: "high",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    closed_at: null,
    ...overrides,
  };
}

describe("OpportunitiesList", () => {
  it("renders each opportunity's company name and links to its detail page", () => {
    render(<OpportunitiesList items={[item()]} />);
    const link = screen.getByRole("link", { name: /barbearia central/i });
    expect(link).toHaveAttribute("href", "/crm/opportunities/o1");
  });

  it("shows the score and stage for each item", () => {
    render(<OpportunitiesList items={[item({ opportunity_score: 88.0 })]} />);
    expect(screen.getByText("88.0")).toBeInTheDocument();
    expect(screen.getByText("Novo")).toBeInTheDocument();
  });

  it("renders multiple opportunities without dropping any", () => {
    render(
      <OpportunitiesList
        items={[item({ id: "o1", company_name: "Empresa A" }), item({ id: "o2", company_name: "Empresa B" })]}
      />
    );
    expect(screen.getByText("Empresa A")).toBeInTheDocument();
    expect(screen.getByText("Empresa B")).toBeInTheDocument();
  });
});
