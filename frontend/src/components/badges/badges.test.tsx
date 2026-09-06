import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TierBadge } from "@/components/badges/tier-badge";
import { ConfidenceBadge } from "@/components/badges/confidence-badge";
import { SiteStateBadge } from "@/components/badges/site-state-badge";
import { RunStatusBadge, AuditStatusBadge } from "@/components/badges/run-status-badge";

describe("TierBadge", () => {
  it("renders the Portuguese label for a known tier", () => {
    render(<TierBadge tier="medium_high" />);
    expect(screen.getByText("Média-alta")).toBeInTheDocument();
  });

  it("renders a distinct 'sem score' state for null — never a fabricated tier", () => {
    render(<TierBadge tier={null} />);
    expect(screen.getByText("Sem score")).toBeInTheDocument();
  });
});

describe("ConfidenceBadge", () => {
  it("always pairs the label with an icon, never color alone", () => {
    render(<ConfidenceBadge confidence="low" />);
    const badge = screen.getByTestId("confidence-badge");
    expect(badge).toHaveTextContent("Baixa");
    expect(badge.querySelector("svg")).toBeInTheDocument();
  });

  it("renders an em-dash when confidence is null", () => {
    render(<ConfidenceBadge confidence={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("SiteStateBadge", () => {
  it("never collapses not_detected into a generic 'no website' label", () => {
    render(<SiteStateBadge state="not_detected" />);
    expect(screen.getByText("Não detectado")).toBeInTheDocument();
  });

  it("distinguishes inconclusive from inaccessible", () => {
    const { rerender } = render(<SiteStateBadge state="inconclusive" />);
    expect(screen.getByText("Inconclusivo")).toBeInTheDocument();
    rerender(<SiteStateBadge state="inaccessible" />);
    expect(screen.getByText("Inacessível")).toBeInTheDocument();
  });

  it("renders 'Não auditado' distinctly when there is no audit at all", () => {
    render(<SiteStateBadge state={null} />);
    expect(screen.getByText("Não auditado")).toBeInTheDocument();
  });
});

describe("RunStatusBadge", () => {
  it("renders each SearchRunStatus with its Portuguese label", () => {
    render(<RunStatusBadge status="partially_completed" />);
    expect(screen.getByText("Parcialmente concluída")).toBeInTheDocument();
  });
});

describe("AuditStatusBadge", () => {
  it("renders the failed state distinctly", () => {
    render(<AuditStatusBadge status="failed" />);
    expect(screen.getByText("Falhou")).toBeInTheDocument();
  });
});
