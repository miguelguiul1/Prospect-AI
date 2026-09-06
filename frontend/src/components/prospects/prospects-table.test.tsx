import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProspectsTable } from "@/components/prospects/prospects-table";
import type { CompanyListItem } from "@/lib/api/types";

function item(overrides: Partial<CompanyListItem> = {}): CompanyListItem {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    canonical_name: "Barbearia Exemplo",
    category_name: "Barbearia",
    category_slug: "barbearia",
    region_name: "Recife",
    region_state: "PE",
    created_at: "2026-09-01T10:00:00Z",
    has_audit: true,
    audit_status: "completed",
    site_state: "not_detected",
    website_quality_score: null,
    opportunity_score: 82.3,
    opportunity_tier: "high",
    opportunity_confidence: "high",
    ...overrides,
  };
}

describe("ProspectsTable", () => {
  it("renders each prospect's name, location, score and tier", () => {
    render(<ProspectsTable items={[item()]} />);
    expect(screen.getAllByText("Barbearia Exemplo").length).toBeGreaterThan(0);
    expect(screen.getAllByText("82.3").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Alta").length).toBeGreaterThan(0);
  });

  it("links each row to its prospect detail page", () => {
    render(<ProspectsTable items={[item()]} />);
    const links = screen.getAllByRole("link", { name: "Barbearia Exemplo" });
    expect(links[0]).toHaveAttribute("href", "/prospects/11111111-1111-1111-1111-111111111111");
  });

  it("never shows a fabricated location when the company has no region", () => {
    render(<ProspectsTable items={[item({ region_name: null, region_state: null })]} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("renders an empty table body without crashing when there are no items", () => {
    const { container } = render(<ProspectsTable items={[]} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(0);
  });
});
