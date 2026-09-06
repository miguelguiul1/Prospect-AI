import { describe, it, expect } from "vitest";
import { builderReducer, createInitialState, childrenOf } from "@/components/prototype-builder/builder-reducer";
import type { ComponentNode } from "@/lib/prototype/types";

function node(id: string, overrides: Partial<ComponentNode> = {}): ComponentNode {
  return { id, type: "text", parentId: null, order: 0, props: {}, styles: {}, ...overrides };
}

describe("builderReducer — ADD_COMPONENT", () => {
  it("adds a root-level component and selects it", () => {
    const state = createInitialState([]);
    const next = builderReducer(state, { type: "ADD_COMPONENT", componentType: "button", parentId: null, newId: "a" });

    expect(next.components).toHaveLength(1);
    expect(next.components[0]).toMatchObject({ id: "a", type: "button", parentId: null, order: 0 });
    expect(next.selectedId).toBe("a");
    expect(next.dirty).toBe(true);
  });

  it("assigns the next sibling order, not always 0", () => {
    let state = createInitialState([]);
    state = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: "a" });
    state = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: "b" });

    const b = state.components.find((c) => c.id === "b")!;
    expect(b.order).toBe(1);
  });

  it("adds inside a given parent when parentId is provided", () => {
    const state = createInitialState([node("root", { type: "container" })]);
    const next = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: "root", newId: "child" });

    expect(next.components.find((c) => c.id === "child")?.parentId).toBe("root");
  });

  it("pushes a history entry so the addition can be undone", () => {
    const state = createInitialState([]);
    const next = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: "a" });
    expect(next.past).toHaveLength(1);
    expect(next.past[0]).toEqual([]);
  });
});

describe("builderReducer — SELECT", () => {
  it("selects and deselects without touching history", () => {
    const state = createInitialState([node("a")]);
    const selected = builderReducer(state, { type: "SELECT", id: "a" });
    expect(selected.selectedId).toBe("a");
    expect(selected.past).toHaveLength(0);

    const deselected = builderReducer(selected, { type: "SELECT", id: null });
    expect(deselected.selectedId).toBeNull();
  });
});

describe("builderReducer — REMOVE_SELECTED", () => {
  it("does nothing when nothing is selected", () => {
    const state = createInitialState([node("a")]);
    const next = builderReducer(state, { type: "REMOVE_SELECTED" });
    expect(next).toBe(state);
  });

  it("removes the selected component", () => {
    let state = createInitialState([node("a"), node("b")]);
    state = builderReducer(state, { type: "SELECT", id: "a" });
    state = builderReducer(state, { type: "REMOVE_SELECTED" });

    expect(state.components.map((c) => c.id)).toEqual(["b"]);
    expect(state.selectedId).toBeNull();
  });

  it("removes a container's entire descendant subtree, never leaving orphans", () => {
    let state = createInitialState([
      node("root", { type: "container" }),
      node("child", { type: "text", parentId: "root" }),
      node("grandchild", { type: "text", parentId: "child" }),
      node("sibling"),
    ]);
    state = builderReducer(state, { type: "SELECT", id: "root" });
    state = builderReducer(state, { type: "REMOVE_SELECTED" });

    expect(state.components.map((c) => c.id).sort()).toEqual(["sibling"]);
  });
});

describe("builderReducer — MOVE_SELECTED", () => {
  it("swaps order with the previous sibling when moving up", () => {
    let state = createInitialState([node("a", { order: 0 }), node("b", { order: 1 })]);
    state = builderReducer(state, { type: "SELECT", id: "b" });
    state = builderReducer(state, { type: "MOVE_SELECTED", direction: "up" });

    expect(state.components.find((c) => c.id === "a")!.order).toBe(1);
    expect(state.components.find((c) => c.id === "b")!.order).toBe(0);
  });

  it("does nothing when already the first sibling", () => {
    let state = createInitialState([node("a", { order: 0 }), node("b", { order: 1 })]);
    state = builderReducer(state, { type: "SELECT", id: "a" });
    const next = builderReducer(state, { type: "MOVE_SELECTED", direction: "up" });
    expect(next).toBe(state);
  });

  it("does nothing when already the last sibling", () => {
    let state = createInitialState([node("a", { order: 0 }), node("b", { order: 1 })]);
    state = builderReducer(state, { type: "SELECT", id: "b" });
    const next = builderReducer(state, { type: "MOVE_SELECTED", direction: "down" });
    expect(next).toBe(state);
  });

  it("only reorders among siblings with the same parent, never across containers", () => {
    let state = createInitialState([
      node("root1", { type: "container", order: 0 }),
      node("root2", { type: "container", order: 1 }),
      node("child", { type: "text", parentId: "root2", order: 0 }),
    ]);
    state = builderReducer(state, { type: "SELECT", id: "child" });
    const next = builderReducer(state, { type: "MOVE_SELECTED", direction: "up" });
    // "child" só tem um irmão (nenhum) dentro de root2 — nada deveria mudar.
    expect(next).toBe(state);
  });
});

describe("builderReducer — UPDATE_PROP and history batching", () => {
  it("updates the given prop without touching other props", () => {
    const state = createInitialState([node("a", { props: { content: "old", other: "keep" } })]);
    const next = builderReducer(state, { type: "UPDATE_PROP", id: "a", scope: "props", key: "content", value: "new" });

    expect(next.components[0].props).toEqual({ content: "new", other: "keep" });
  });

  it("batches consecutive edits into a single history entry until COMMIT_HISTORY", () => {
    let state = createInitialState([node("a", { props: { content: "" } })]);
    state = builderReducer(state, { type: "UPDATE_PROP", id: "a", scope: "props", key: "content", value: "o" });
    state = builderReducer(state, { type: "UPDATE_PROP", id: "a", scope: "props", key: "content", value: "ol" });
    state = builderReducer(state, { type: "UPDATE_PROP", id: "a", scope: "props", key: "content", value: "olá" });

    expect(state.past).toHaveLength(1);
    expect(state.components[0].props.content).toBe("olá");
  });

  it("starts a new history entry after COMMIT_HISTORY", () => {
    let state = createInitialState([node("a", { props: { content: "" } })]);
    state = builderReducer(state, { type: "UPDATE_PROP", id: "a", scope: "props", key: "content", value: "a" });
    state = builderReducer(state, { type: "COMMIT_HISTORY" });
    state = builderReducer(state, { type: "UPDATE_PROP", id: "a", scope: "props", key: "content", value: "b" });

    expect(state.past).toHaveLength(2);
  });

  it("edits the styles scope independently of props", () => {
    const state = createInitialState([node("a")]);
    const next = builderReducer(state, { type: "UPDATE_PROP", id: "a", scope: "styles", key: "color", value: "#fff" });
    expect(next.components[0].styles).toEqual({ color: "#fff" });
    expect(next.components[0].props).toEqual({});
  });
});

describe("builderReducer — UNDO/REDO", () => {
  it("does nothing when there is no history", () => {
    const state = createInitialState([node("a")]);
    expect(builderReducer(state, { type: "UNDO" })).toBe(state);
    expect(builderReducer(state, { type: "REDO" })).toBe(state);
  });

  it("restores the previous tree on UNDO and can REDO forward again", () => {
    let state = createInitialState([]);
    state = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: "a" });
    state = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: "b" });
    expect(state.components).toHaveLength(2);

    state = builderReducer(state, { type: "UNDO" });
    expect(state.components.map((c) => c.id)).toEqual(["a"]);

    state = builderReducer(state, { type: "UNDO" });
    expect(state.components).toHaveLength(0);

    state = builderReducer(state, { type: "REDO" });
    expect(state.components.map((c) => c.id)).toEqual(["a"]);
  });

  it("clears the redo stack once a new change is made after an undo", () => {
    let state = createInitialState([]);
    state = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: "a" });
    state = builderReducer(state, { type: "UNDO" });
    expect(state.future).toHaveLength(1);

    state = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: "c" });
    expect(state.future).toHaveLength(0);
  });

  it("caps history at 50 entries", () => {
    let state = createInitialState([]);
    for (let i = 0; i < 60; i++) {
      state = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: `n${i}` });
    }
    expect(state.past.length).toBeLessThanOrEqual(50);
  });
});

describe("builderReducer — SET_MODE", () => {
  it("deselects the current component when switching to preview", () => {
    let state = createInitialState([node("a")]);
    state = builderReducer(state, { type: "SELECT", id: "a" });
    state = builderReducer(state, { type: "SET_MODE", mode: "preview" });

    expect(state.mode).toBe("preview");
    expect(state.selectedId).toBeNull();
  });
});

describe("builderReducer — MARK_SAVED", () => {
  it("clears the dirty flag without touching the tree", () => {
    let state = createInitialState([]);
    state = builderReducer(state, { type: "ADD_COMPONENT", componentType: "text", parentId: null, newId: "a" });
    expect(state.dirty).toBe(true);

    state = builderReducer(state, { type: "MARK_SAVED" });
    expect(state.dirty).toBe(false);
    expect(state.components).toHaveLength(1);
  });
});

describe("childrenOf", () => {
  it("returns direct children sorted by order, never grandchildren", () => {
    const components = [
      node("root", { type: "container" }),
      node("b", { parentId: "root", order: 1 }),
      node("a", { parentId: "root", order: 0 }),
      node("grandchild", { parentId: "b", order: 0 }),
    ];
    expect(childrenOf(components, "root").map((c) => c.id)).toEqual(["a", "b"]);
  });

  it("returns root-level components when parentId is null", () => {
    const components = [node("root1"), node("root2"), node("child", { parentId: "root1" })];
    expect(childrenOf(components, null).map((c) => c.id)).toEqual(["root1", "root2"]);
  });
});
