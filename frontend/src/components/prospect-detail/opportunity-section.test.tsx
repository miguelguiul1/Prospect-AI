import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OpportunitySection } from "@/components/prospect-detail/opportunity-section";
import type { OpportunityScoreDetail } from "@/lib/api/types";

describe("OpportunitySection", () => {
  it("explains the precondition instead of showing a fabricated score", () => {
    render(<OpportunitySection score={null} />);
    expect(screen.getByText(/ainda não calculado/i)).toBeInTheDocument();
  });

  it("renders score, tier, confidence and scoring version", () => {
    const score: OpportunityScoreDetail = {
      id: "s1",
      score: 72.5,
      tier: "medium_high",
      confidence: "medium",
      scoring_version: "v1",
      breakdown: null,
      created_at: "2026-09-01T10:00:00Z",
      updated_at: "2026-09-01T10:00:00Z",
    };
    render(<OpportunitySection score={score} />);
    expect(screen.getByText("72.5")).toBeInTheDocument();
    expect(screen.getByText("Média-alta")).toBeInTheDocument();
    expect(screen.getByText("Média")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
  });

  it("always states the score is not a conversion probability", () => {
    const score: OpportunityScoreDetail = {
      id: "s1",
      score: 50,
      tier: "medium",
      confidence: "low",
      scoring_version: "v1",
      breakdown: null,
      created_at: "2026-09-01T10:00:00Z",
      updated_at: "2026-09-01T10:00:00Z",
    };
    render(<OpportunitySection score={score} />);
    expect(screen.getByText(/não é uma probabilidade de conversão/i)).toBeInTheDocument();
  });
});
