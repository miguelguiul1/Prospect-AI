import { describe, it, expect } from "vitest";
import { COMPONENT_REGISTRY, COMPONENT_LIST, definitionFor } from "@/lib/prototype/component-registry";
import { COMPONENT_TYPES } from "@/lib/prototype/types";

describe("COMPONENT_REGISTRY", () => {
  it("has exactly one definition per type declared in COMPONENT_TYPES — kept in sync with the backend allowlist", () => {
    expect(Object.keys(COMPONENT_REGISTRY).sort()).toEqual([...COMPONENT_TYPES].sort());
  });

  it("every definition's own `type` field matches its registry key", () => {
    for (const [key, def] of Object.entries(COMPONENT_REGISTRY)) {
      expect(def.type).toBe(key);
    }
  });

  it("layout and interface containers accept children; content and form leaves do not", () => {
    expect(COMPONENT_REGISTRY.container.acceptsChildren).toBe(true);
    expect(COMPONENT_REGISTRY.section.acceptsChildren).toBe(true);
    expect(COMPONENT_REGISTRY.row.acceptsChildren).toBe(true);
    expect(COMPONENT_REGISTRY.column.acceptsChildren).toBe(true);
    expect(COMPONENT_REGISTRY.card.acceptsChildren).toBe(true);

    expect(COMPONENT_REGISTRY.text.acceptsChildren).toBe(false);
    expect(COMPONENT_REGISTRY.button.acceptsChildren).toBe(false);
    expect(COMPONENT_REGISTRY.image.acceptsChildren).toBe(false);
    expect(COMPONENT_REGISTRY.divider.acceptsChildren).toBe(false);
  });

  it("COMPONENT_LIST has the same length as the registry — nothing lost in translation", () => {
    expect(COMPONENT_LIST).toHaveLength(Object.keys(COMPONENT_REGISTRY).length);
  });

  it("definitionFor returns undefined for a type outside the catalog, never a fabricated default", () => {
    expect(definitionFor("script")).toBeUndefined();
    expect(definitionFor("iframe")).toBeUndefined();
  });

  it("definitionFor resolves a real type", () => {
    expect(definitionFor("button")?.label).toBe("Button");
  });
});
