import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiscoverySection } from "@/components/prospect-detail/discovery-section";

describe("DiscoverySection", () => {
  it("shows an empty state when no source is registered", () => {
    render(<DiscoverySection sources={[]} />);
    expect(screen.getByText(/nenhuma fonte registrada/i)).toBeInTheDocument();
  });

  it("lists each source with its external id and confidence", () => {
    render(
      <DiscoverySection
        sources={[
          {
            id: "s1",
            source: "google_places",
            external_id: "ChIJ123",
            source_url: null,
            latitude: null,
            longitude: null,
            confidence: "high",
            first_seen_at: "2026-09-01T10:00:00Z",
            last_seen_at: "2026-09-02T10:00:00Z",
          },
        ]}
      />
    );
    expect(screen.getByText("google_places")).toBeInTheDocument();
    expect(screen.getByText(/ChIJ123/)).toBeInTheDocument();
  });
});
