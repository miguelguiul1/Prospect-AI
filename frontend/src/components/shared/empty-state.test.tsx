import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "@/components/shared/empty-state";

describe("EmptyState", () => {
  it("renders the title and description with a status role for assistive tech", () => {
    render(<EmptyState title="Ainda não existem prospects." description="Execute sua primeira pesquisa." />);
    expect(screen.getByRole("status")).toHaveTextContent("Ainda não existem prospects.");
    expect(screen.getByText("Execute sua primeira pesquisa.")).toBeInTheDocument();
  });

  it("renders an optional call-to-action", () => {
    render(<EmptyState title="Vazio" action={<button>Nova pesquisa</button>} />);
    expect(screen.getByRole("button", { name: "Nova pesquisa" })).toBeInTheDocument();
  });
});
