import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ActivityItem } from "@/lib/api/types";

const createActivityAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "success" }));
const completeActivityAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "success" }));
vi.mock("@/app/crm/actions", () => ({
  createActivityAction: (...args: Parameters<typeof createActivityAction>) => createActivityAction(...args),
  completeActivityAction: (...args: Parameters<typeof completeActivityAction>) => completeActivityAction(...args),
}));

const { TimelinePanel } = await import("@/components/crm/timeline-panel");

function activity(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: "a1",
    type: "note",
    title: null,
    description: "Ligou pedindo mais informações",
    status: null,
    due_at: null,
    completed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("TimelinePanel", () => {
  it("shows an empty-state message when there are no activities", () => {
    render(<TimelinePanel opportunityId="o1" activities={[]} />);
    expect(screen.getByText(/nenhuma atividade ainda/i)).toBeInTheDocument();
  });

  it("renders a note's description", () => {
    render(<TimelinePanel opportunityId="o1" activities={[activity()]} />);
    expect(screen.getByText("Ligou pedindo mais informações")).toBeInTheDocument();
  });

  it("shows a strikethrough label for a completed task", () => {
    render(
      <TimelinePanel
        opportunityId="o1"
        activities={[activity({ id: "a2", type: "task", title: "Follow-up", status: "done" })]}
      />
    );
    expect(screen.getByText("Follow-up")).toHaveClass("line-through");
  });

  it("shows a toggle button for a pending task", () => {
    render(
      <TimelinePanel
        opportunityId="o1"
        activities={[activity({ id: "a3", type: "task", title: "Ligar amanhã", status: "open" })]}
      />
    );
    expect(screen.getByRole("button", { name: /concluir tarefa/i })).toBeInTheDocument();
  });

  it("the quick-add form offers note and task types", () => {
    render(<TimelinePanel opportunityId="o1" activities={[]} />);
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toContain("note");
    expect(optionValues).toContain("task");
  });
});
