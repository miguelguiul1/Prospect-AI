import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IdentitySection } from "@/components/prospect-detail/identity-section";
import type { CompanyDetail } from "@/lib/api/types";

function company(overrides: Partial<CompanyDetail> = {}): CompanyDetail {
  return {
    id: "c1",
    canonical_name: "Barbearia Exemplo",
    status: "active",
    category_name: "Barbearia",
    category_slug: "barbearia",
    region_name: "Recife",
    region_state: "PE",
    created_at: "2026-09-01T10:00:00Z",
    sources: [],
    evidence: [],
    latest_audit: null,
    latest_score: null,
    latest_brief: null,
    ...overrides,
  };
}

describe("IdentitySection", () => {
  it("shows 'Não observado' instead of inventing an address/phone when absent", () => {
    render(<IdentitySection company={company()} />);
    expect(screen.getAllByText("Não observado").length).toBe(2);
  });

  it("renders the real address/phone when present in Evidence", () => {
    render(
      <IdentitySection
        company={company({
          evidence: [
            {
              id: "e1",
              field: "address",
              value: "Rua Exemplo, 123",
              state: "confirmed",
              source: "google_places",
              source_url: null,
              method: "structured_field",
              confidence: "high",
              collected_at: "2026-09-01T10:00:00Z",
            },
          ],
        })}
      />
    );
    expect(screen.getByText("Rua Exemplo, 123")).toBeInTheDocument();
  });

  it("shows the Company ID for traceability", () => {
    render(<IdentitySection company={company({ id: "abc-123" })} />);
    expect(screen.getByText("abc-123")).toBeInTheDocument();
  });
});
