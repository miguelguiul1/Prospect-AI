import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StageBadge } from "@/components/crm/stage-badge";
import type { PipelineStage } from "@/lib/api/types";

function stage(overrides: Partial<PipelineStage> = {}): PipelineStage {
  return { id: "s1", key: "new", name: "Novo", order: 1, is_won: false, is_lost: false, ...overrides };
}

describe("StageBadge", () => {
  it("renders the stage name", () => {
    render(<StageBadge stage={stage({ name: "Reunião" })} />);
    expect(screen.getByText("Reunião")).toBeInTheDocument();
  });

  it("uses a distinct style for a won stage vs a regular one", () => {
    const { rerender } = render(<StageBadge stage={stage({ key: "won", name: "Ganho", is_won: true })} />);
    const wonBadge = screen.getByText("Ganho");
    const wonClass = wonBadge.className;

    rerender(<StageBadge stage={stage()} />);
    const regularBadge = screen.getByText("Novo");
    expect(regularBadge.className).not.toBe(wonClass);
  });

  it("uses a distinct style for a lost stage", () => {
    render(<StageBadge stage={stage({ key: "lost", name: "Perdido", is_lost: true })} />);
    expect(screen.getByText("Perdido")).toBeInTheDocument();
  });
});
