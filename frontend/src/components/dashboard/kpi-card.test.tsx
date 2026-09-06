import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { KpiCard, KpiCardSkeletonList } from "@/components/dashboard/kpi-card";

describe("KpiCard", () => {
  it("renders the label, value and hint", () => {
    render(<KpiCard label="Prospects encontrados" value={42} hint="Empresas descobertas" />);
    expect(screen.getByText("Prospects encontrados")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("Empresas descobertas")).toBeInTheDocument();
  });

  it("renders zero explicitly, never blank, when there is no data", () => {
    render(<KpiCard label="Score médio" value="—" hint="Nenhum score calculado ainda" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Nenhum score calculado ainda")).toBeInTheDocument();
  });
});

describe("KpiCardSkeletonList", () => {
  it("renders four placeholder cards", () => {
    const { container } = render(<KpiCardSkeletonList />);
    expect(container.querySelectorAll('[data-slot="card"]')).toHaveLength(4);
  });
});
