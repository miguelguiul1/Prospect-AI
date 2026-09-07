import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const changeStageAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "success", message: "Etapa atualizada." }));
vi.mock("@/app/crm/actions", () => ({
  changeStageAction: (...args: Parameters<typeof changeStageAction>) => changeStageAction(...args),
}));

const { StageSelect } = await import("@/components/crm/stage-select");

const STAGES = [
  { id: "s1", key: "new", name: "Novo", order: 1, is_won: false, is_lost: false },
  { id: "s2", key: "qualified", name: "Qualificado", order: 2, is_won: false, is_lost: false },
];

describe("StageSelect", () => {
  it("shows the current stage as selected", () => {
    render(<StageSelect opportunityId="o1" stages={STAGES} currentStageKey="new" />);
    expect(screen.getByRole("combobox")).toHaveValue("new");
  });

  it("submits automatically when the stage changes — no separate save button", async () => {
    render(<StageSelect opportunityId="o1" stages={STAGES} currentStageKey="new" />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "qualified");

    await waitFor(() => expect(changeStageAction).toHaveBeenCalled());
  });

  it("includes the opportunityId as a hidden field", () => {
    const { container } = render(<StageSelect opportunityId="opp-123" stages={STAGES} currentStageKey="new" />);
    const hidden = container.querySelector('input[name="opportunityId"]') as HTMLInputElement;
    expect(hidden.value).toBe("opp-123");
  });
});
