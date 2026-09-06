import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaginationBar } from "@/components/shared/pagination-bar";

describe("PaginationBar", () => {
  it("renders nothing when everything fits on one page — never a fake paginator", () => {
    const { container } = render(
      <PaginationBar total={5} limit={20} offset={0} buildHref={(o) => `/x?offset=${o}`} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("disables 'Anterior' on the first page", () => {
    render(<PaginationBar total={50} limit={20} offset={0} buildHref={(o) => `/x?offset=${o}`} />);
    expect(screen.getByRole("button", { name: /anterior/i })).toBeDisabled();
    expect(screen.getByRole("link", { name: /próxima/i })).toHaveAttribute("href", "/x?offset=20");
  });

  it("disables 'Próxima' on the last page", () => {
    render(<PaginationBar total={50} limit={20} offset={40} buildHref={(o) => `/x?offset=${o}`} />);
    expect(screen.getByRole("button", { name: /próxima/i })).toBeDisabled();
    expect(screen.getByRole("link", { name: /anterior/i })).toHaveAttribute("href", "/x?offset=20");
  });

  it("shows the real total and current page — never a guessed count", () => {
    render(<PaginationBar total={45} limit={20} offset={20} buildHref={(o) => `/x?offset=${o}`} />);
    expect(screen.getByText(/página 2 de 3/i)).toBeInTheDocument();
    expect(screen.getByText(/45 no total/)).toBeInTheDocument();
  });
});
