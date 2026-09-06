import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BreakdownSection } from "@/components/prospect-detail/breakdown-section";
import type { OpportunityBreakdown } from "@/lib/api/types";

const breakdown: OpportunityBreakdown = {
  scoring_version: "v1",
  final_score: 62.3,
  available_weight: 0.65,
  dimensions: {
    website_gap: {
      raw: 100,
      weight: 0.25,
      contribution: 25,
      reason: "nenhum site próprio foi detectado",
      evidence_refs: [],
    },
    business_visibility: {
      raw: 90,
      weight: 0.15,
      contribution: 13.5,
      reason: "120 avaliações públicas, nota 4.7/5",
      evidence_refs: [{ field: "rating", value: "4.7", evidence_id: "ev1" }],
    },
    segment_fit: {
      raw: null,
      weight: 0.15,
      contribution: null,
      reason: "empresa sem categoria atribuída — dimensão excluída.",
      evidence_refs: [],
    },
  },
};

describe("BreakdownSection", () => {
  it("shows a placeholder when there is no breakdown yet", () => {
    render(<BreakdownSection breakdown={null} />);
    expect(screen.getByText(/sem breakdown disponível/i)).toBeInTheDocument();
  });

  it("renders every dimension with its own reason — never just the final number", () => {
    render(<BreakdownSection breakdown={breakdown} />);
    expect(screen.getByText(/nenhum site próprio foi detectado/i)).toBeInTheDocument();
    expect(screen.getByText(/120 avaliações públicas/i)).toBeInTheDocument();
  });

  it("marks an excluded dimension explicitly instead of showing a fake 0", () => {
    render(<BreakdownSection breakdown={breakdown} />);
    expect(screen.getByText(/excluído do cálculo/i)).toBeInTheDocument();
  });

  it("shows the evidence reference chips for a dimension that has them", () => {
    render(<BreakdownSection breakdown={breakdown} />);
    expect(screen.getByText("rating: 4.7")).toBeInTheDocument();
  });

  it("shows each dimension's weight as a percentage", () => {
    render(<BreakdownSection breakdown={breakdown} />);
    expect(screen.getByText("peso 25%")).toBeInTheDocument();
  });
});
