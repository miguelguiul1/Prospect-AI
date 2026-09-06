import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WebsiteSection } from "@/components/prospect-detail/website-section";
import type { AuditSnapshotDetail } from "@/lib/api/types";

function audit(overrides: Partial<AuditSnapshotDetail> = {}): AuditSnapshotDetail {
  return {
    id: "a1",
    run_id: "r1",
    status: "completed",
    site_state: "confirmed",
    website_url: "https://empresa.example.com",
    error_code: null,
    error_message: null,
    started_at: "2026-09-01T10:00:00Z",
    finished_at: "2026-09-01T10:00:01Z",
    created_at: "2026-09-01T10:00:01Z",
    website_quality: {
      score: 80,
      components: null,
      confidence: "high",
      limitations: null,
      signals: { https: true, status_code: 200, response_time_ms: 120.5, redirect_count: 0 },
    },
    ...overrides,
  };
}

describe("WebsiteSection", () => {
  it("explains that no audit has run yet, without pretending one exists", () => {
    render(<WebsiteSection audit={null} />);
    expect(screen.getByText(/nenhuma auditoria digital foi executada/i)).toBeInTheDocument();
  });

  it("shows the hedged explanation for not_detected — never a bare negative claim", () => {
    render(<WebsiteSection audit={audit({ site_state: "not_detected", website_quality: null, website_url: null })} />);
    expect(screen.getByText(/não significa necessariamente que a empresa não tenha um site/i)).toBeInTheDocument();
  });

  it("renders real signals (https, status, response time) when the site is confirmed", () => {
    render(<WebsiteSection audit={audit()} />);
    expect(screen.getByText("Sim")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("120.5 ms")).toBeInTheDocument();
  });
});
