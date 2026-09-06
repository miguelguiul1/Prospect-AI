import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/app/pesquisas/nova/actions", () => ({
  startSearchAction: vi.fn(),
}));

const { NewSearchForm } = await import("@/components/discovery/new-search-form");

describe("NewSearchForm", () => {
  it("requires a category field", () => {
    render(<NewSearchForm />);
    expect(screen.getByLabelText(/categoria/i)).toBeRequired();
  });

  it("caps max_results at the same hard limit as the backend (60)", () => {
    render(<NewSearchForm />);
    expect(screen.getByLabelText(/quantidade máxima/i)).toHaveAttribute("max", "60");
  });

  it("never lists a discovery provider that isn't actually implemented", () => {
    render(<NewSearchForm />);
    expect(screen.getByText(/único provider implementado/i)).toHaveTextContent("Google Places");
  });

  it("defaults country to BR without requiring the user to type it", () => {
    render(<NewSearchForm />);
    expect(screen.getByLabelText(/país/i)).toHaveValue("BR");
  });
});
