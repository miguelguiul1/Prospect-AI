import { describe, it, expect, vi, beforeEach } from "vitest";

// Primeiro teste deste projeto a exercitar uma Server Action real desta
// página diretamente (não só via um mock passado a `ActionButton`) —
// Prompt 11, seção 3 do relatório de auditoria de cobertura do Prompt 10
// já tinha identificado esta lacuna nas outras actions do arquivo.
const createPrototype = vi.fn();
const generatePrototype = vi.fn();
vi.mock("@/lib/api/prototypes", () => ({
  createPrototype: (...args: unknown[]) => createPrototype(...args),
  generatePrototype: (...args: unknown[]) => generatePrototype(...args),
}));

const redirect = vi.fn((path: string) => {
  throw new Error(`NEXT_REDIRECT:${path}`);
});
vi.mock("next/navigation", () => ({ redirect: (path: string) => redirect(path) }));

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

vi.mock("@/lib/api/audit", () => ({ runDigitalAudit: vi.fn() }));
vi.mock("@/lib/api/scoring", () => ({ computeOpportunityScore: vi.fn() }));
vi.mock("@/lib/api/briefing", () => ({ generateSalesBrief: vi.fn() }));

// `lib/api/client.ts` importa o pacote `server-only` — inerte fora do
// bundler do Next.js, mas ainda lança fora dele (mesmo cuidado de
// `sales-brief-section.test.tsx`, aqui necessário porque este teste
// importa `actions.ts` de verdade, não um mock dele).
class FakeApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(message: string, status: number, code: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}
vi.mock("@/lib/api/client", () => ({ ApiError: FakeApiError }));

const { generatePrototypeAction } = await import("@/app/prospects/[companyId]/actions");

function formDataWithCompanyId(companyId: string): FormData {
  const formData = new FormData();
  formData.set("companyId", companyId);
  return formData;
}

describe("generatePrototypeAction", () => {
  beforeEach(() => {
    createPrototype.mockReset();
    generatePrototype.mockReset();
    redirect.mockClear();
  });

  it("creates a prototype linked to the company, generates it, then redirects to the builder", async () => {
    createPrototype.mockResolvedValueOnce({ id: "proto-123" });
    generatePrototype.mockResolvedValueOnce({ id: "gen-1", status: "succeeded" });

    await expect(generatePrototypeAction({ status: "idle" }, formDataWithCompanyId("company-1"))).rejects.toThrow(
      "NEXT_REDIRECT:/prototypes/proto-123"
    );

    expect(createPrototype).toHaveBeenCalledWith({ name: "Novo protótipo", companyId: "company-1" });
    expect(generatePrototype).toHaveBeenCalledWith("proto-123");
    expect(redirect).toHaveBeenCalledWith("/prototypes/proto-123");
  });

  it("returns a real error and never redirects when creating the prototype fails", async () => {
    createPrototype.mockRejectedValueOnce(new Error("falha de rede"));

    const result = await generatePrototypeAction({ status: "idle" }, formDataWithCompanyId("company-1"));

    expect(result.status).toBe("error");
    expect(redirect).not.toHaveBeenCalled();
    expect(generatePrototype).not.toHaveBeenCalled();
  });

  it("returns a real error and never redirects when the generation completes with status failed", async () => {
    createPrototype.mockResolvedValueOnce({ id: "proto-789" });
    generatePrototype.mockResolvedValueOnce({
      id: "gen-2",
      status: "failed",
      errorMessage: "Empresa sem Evidence nem AuditSnapshot.",
    });

    const result = await generatePrototypeAction({ status: "idle" }, formDataWithCompanyId("company-1"));

    expect(result).toEqual({ status: "error", message: "Empresa sem Evidence nem AuditSnapshot." });
    expect(redirect).not.toHaveBeenCalled();
  });

  it("returns a real error and never redirects when generation itself fails to even start", async () => {
    createPrototype.mockResolvedValueOnce({ id: "proto-456" });
    generatePrototype.mockRejectedValueOnce(new Error("provider indisponível"));

    const result = await generatePrototypeAction({ status: "idle" }, formDataWithCompanyId("company-1"));

    expect(result.status).toBe("error");
    expect(redirect).not.toHaveBeenCalled();
  });
});
