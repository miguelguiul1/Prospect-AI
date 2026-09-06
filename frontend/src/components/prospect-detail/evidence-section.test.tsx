import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvidenceSection } from "@/components/prospect-detail/evidence-section";
import type { EvidenceItem } from "@/lib/api/types";

function evidence(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    id: "e1",
    field: "website",
    value: "https://empresa.example.com",
    state: "confirmed",
    source: "google_places",
    source_url: null,
    method: "structured_field",
    confidence: "high",
    collected_at: "2026-09-06T10:00:00Z",
    ...overrides,
  };
}

describe("EvidenceSection", () => {
  it("shows an empty state when there is no evidence yet", () => {
    render(<EvidenceSection evidence={[]} />);
    expect(screen.getByText(/nenhuma evidência coletada ainda/i)).toBeInTheDocument();
  });

  it("marks confirmed evidence distinctly from unconfirmed", () => {
    render(<EvidenceSection evidence={[evidence()]} />);
    expect(screen.getByText("confirmado")).toBeInTheDocument();
  });

  it("shows the hedged explanation for not_detected evidence — never treats absence as fact", () => {
    render(
      <EvidenceSection
        evidence={[evidence({ field: "website", value: null, state: "not_detected" })]}
      />
    );
    expect(
      screen.getByText(/não significa necessariamente que ele não exista/i)
    ).toBeInTheDocument();
  });

  it("always shows provenance: source and collection date", () => {
    render(<EvidenceSection evidence={[evidence()]} />);
    expect(screen.getByText(/fonte: google_places/i)).toBeInTheDocument();
  });
});
