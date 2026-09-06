import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorState } from "@/components/shared/error-state";

describe("ErrorState", () => {
  it("never renders a raw stack trace — only the pre-formatted message", () => {
    render(<ErrorState message="Não foi possível conectar à API." />);
    expect(screen.getByText("Não foi possível conectar à API.")).toBeInTheDocument();
    expect(screen.queryByText(/at\s+\w+\s+\(/)).not.toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Falhou." onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("omits the retry button when onRetry is not provided", () => {
    render(<ErrorState message="Falhou." />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
