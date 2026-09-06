import { describe, it, expect } from "vitest";
import {
  formatDateTime,
  formatScore,
  TIER_LABEL,
  SITE_STATE_LABEL,
  evidenceFieldLabel,
  dimensionLabel,
} from "@/lib/format";

describe("formatDateTime", () => {
  it("returns em-dash for null/undefined", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
  });

  it("returns em-dash for an invalid date string", () => {
    expect(formatDateTime("not-a-date")).toBe("—");
  });

  it("formats a valid ISO date in pt-BR", () => {
    const result = formatDateTime("2026-09-06T10:30:00Z");
    expect(result).toMatch(/\d{2}\/\d{2}\/\d{4}/);
  });
});

describe("formatScore", () => {
  it("returns em-dash for null/undefined", () => {
    expect(formatScore(null)).toBe("—");
    expect(formatScore(undefined)).toBe("—");
  });

  it("formats a number with one decimal place", () => {
    expect(formatScore(72)).toBe("72.0");
    expect(formatScore(72.53)).toBe("72.5");
  });

  it("never returns a fabricated value for zero", () => {
    expect(formatScore(0)).toBe("0.0");
  });
});

describe("label maps", () => {
  it("cover every OpportunityTier value", () => {
    expect(Object.keys(TIER_LABEL).sort()).toEqual(
      ["high", "low", "medium", "medium_high", "very_low"].sort()
    );
  });

  it("cover every DataState value", () => {
    expect(Object.keys(SITE_STATE_LABEL).sort()).toEqual(
      ["confirmed", "inaccessible", "inconclusive", "not_checked", "not_detected", "stale"].sort()
    );
  });

  it("evidenceFieldLabel falls back to the raw field name when unmapped", () => {
    expect(evidenceFieldLabel("phone")).toBe("Telefone");
    expect(evidenceFieldLabel("campo_desconhecido")).toBe("campo_desconhecido");
  });

  it("dimensionLabel falls back to the raw key when unmapped", () => {
    expect(dimensionLabel("website_gap")).toBe("Ausência de site");
    expect(dimensionLabel("dimensao_nova")).toBe("dimensao_nova");
  });
});
