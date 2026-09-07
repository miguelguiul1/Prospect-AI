import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const closeOpportunityAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "success", message: "Oportunidade marcada como ganha." }));
const reopenOpportunityAction = vi.fn(async (_prev: unknown, _formData: FormData) => ({ status: "success", message: "Oportunidade reaberta." }));
vi.mock("@/app/crm/actions", () => ({
  closeOpportunityAction: (...args: Parameters<typeof closeOpportunityAction>) => closeOpportunityAction(...args),
  reopenOpportunityAction: (...args: Parameters<typeof reopenOpportunityAction>) => reopenOpportunityAction(...args),
}));

const { OpportunityActions } = await import("@/components/crm/opportunity-actions");

describe("OpportunityActions", () => {
  it("shows Ganhar/Perder for an open opportunity", () => {
    render(<OpportunityActions opportunityId="o1" status="open" />);
    expect(screen.getByRole("button", { name: /ganhar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /perder/i })).toBeInTheDocument();
  });

  it("shows Reabrir for a closed opportunity, not Ganhar/Perder", () => {
    render(<OpportunityActions opportunityId="o1" status="won" />);
    expect(screen.getByRole("button", { name: /reabrir/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /ganhar/i })).not.toBeInTheDocument();
  });

  it("submits the 'won' outcome when Ganhar is clicked", async () => {
    render(<OpportunityActions opportunityId="o1" status="open" />);
    await userEvent.click(screen.getByRole("button", { name: /ganhar/i }));
    await waitFor(() => expect(closeOpportunityAction).toHaveBeenCalled());
  });

  it("calls reopen when Reabrir is clicked", async () => {
    render(<OpportunityActions opportunityId="o1" status="lost" />);
    await userEvent.click(screen.getByRole("button", { name: /reabrir/i }));
    await waitFor(() => expect(reopenOpportunityAction).toHaveBeenCalled());
  });
});
