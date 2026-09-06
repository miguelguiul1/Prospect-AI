import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WebsiteQualitySection } from "@/components/prospect-detail/website-quality-section";
import type { AuditSnapshotDetail } from "@/lib/api/types";

describe("WebsiteQualitySection", () => {
  it("explains 'not evaluable' instead of showing a fake 0 when the site wasn't confirmed", () => {
    render(
      <WebsiteQualitySection
        audit={{
          id: "a1",
          run_id: "r1",
          status: "completed",
          site_state: "not_detected",
          website_url: null,
          error_code: null,
          error_message: null,
          started_at: null,
          finished_at: null,
          created_at: "2026-09-06T10:00:00Z",
          website_quality: {
            score: null,
            components: null,
            confidence: null,
            limitations: ["site não confirmado como acessível"],
            signals: null,
          },
        }}
      />
    );
    expect(screen.getByText(/site não confirmado como acessível/i)).toBeInTheDocument();
  });

  it("renders the score and per-dimension components when available", () => {
    const audit: AuditSnapshotDetail = {
      id: "a1",
      run_id: "r1",
      status: "completed",
      site_state: "confirmed",
      website_url: "https://x.com",
      error_code: null,
      error_message: null,
      started_at: null,
      finished_at: null,
      created_at: "2026-09-06T10:00:00Z",
      website_quality: {
        score: 69,
        components: { security: 100, seo: 55, content: 40, ux: 50, technical: 100 },
        confidence: "high",
        limitations: [],
        signals: null,
      },
    };
    render(<WebsiteQualitySection audit={audit} />);
    expect(screen.getByText("69.0")).toBeInTheDocument();
    expect(screen.getByText("Segurança")).toBeInTheDocument();
  });
});
