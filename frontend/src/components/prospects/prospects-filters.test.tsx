import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProspectsFilters } from "@/components/prospects/prospects-filters";
import type { FilterOptionsResponse } from "@/lib/api/types";

const filterOptions: FilterOptionsResponse = {
  categories: [{ slug: "barbearia", name: "Barbearia" }],
  regions: [{ name: "Recife", state: "PE" }],
};

describe("ProspectsFilters", () => {
  it("never invents a filter option that doesn't exist in the backend data", () => {
    render(<ProspectsFilters filterOptions={filterOptions} initialValues={{}} />);
    const categorySelect = screen.getByLabelText("Segmento") as HTMLSelectElement;
    const options = Array.from(categorySelect.options).map((o) => o.value);
    expect(options).toEqual(["", "barbearia"]);
  });

  it("is a real GET form so filters are shareable/bookmarkable URLs", () => {
    const { container } = render(<ProspectsFilters filterOptions={filterOptions} initialValues={{}} />);
    const form = container.querySelector("form")!;
    expect(form).toHaveAttribute("method", "get");
  });

  it("pre-fills the search input from the current URL state", () => {
    render(<ProspectsFilters filterOptions={filterOptions} initialValues={{ q: "padaria" }} />);
    expect(screen.getByLabelText("Buscar por nome")).toHaveValue("padaria");
  });
});
