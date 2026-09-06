import type { BuilderMode, ComponentNode, ComponentType, PrimitiveValue } from "@/lib/prototype/types";

/**
 * Estado central do Builder — um `useReducer` puro, sem nenhuma biblioteca
 * de estado nova (pedido explícito da Fase 6). Undo/redo é uma pilha de
 * snapshots da árvore de componentes: simples o suficiente para caber
 * nesta fase (seção 13 do Prompt 09 — "se a arquitetura permitir
 * facilmente, adicione").
 *
 * Edição de propriedade (`UPDATE_PROP`) NÃO empilha um snapshot a cada
 * tecla digitada — isso inundaria o histórico. Um snapshot é tirado uma
 * vez no início de uma "sessão de edição" (`historyLocked` controla isso)
 * e a sessão é fechada com `COMMIT_HISTORY` (disparado no `onBlur` do
 * campo) ou por qualquer outra ação estrutural.
 */

const MAX_HISTORY = 50;

export interface BuilderState {
  components: ComponentNode[];
  selectedId: string | null;
  mode: BuilderMode;
  past: ComponentNode[][];
  future: ComponentNode[][];
  dirty: boolean;
  historyLocked: boolean;
}

export type BuilderAction =
  | { type: "LOAD"; components: ComponentNode[] }
  | { type: "ADD_COMPONENT"; componentType: ComponentType; parentId: string | null; newId: string }
  | { type: "SELECT"; id: string | null }
  | { type: "REMOVE_SELECTED" }
  | { type: "MOVE_SELECTED"; direction: "up" | "down" }
  | { type: "UPDATE_PROP"; id: string; scope: "props" | "styles"; key: string; value: PrimitiveValue }
  | { type: "COMMIT_HISTORY" }
  | { type: "SET_MODE"; mode: BuilderMode }
  | { type: "UNDO" }
  | { type: "REDO" }
  | { type: "MARK_SAVED" };

export function createInitialState(components: ComponentNode[]): BuilderState {
  return {
    components,
    selectedId: null,
    mode: "edit",
    past: [],
    future: [],
    dirty: false,
    historyLocked: false,
  };
}

function pushHistory(state: BuilderState): Pick<BuilderState, "past" | "future"> {
  const past = [...state.past, state.components].slice(-MAX_HISTORY);
  return { past, future: [] };
}

function descendantIds(components: ComponentNode[], rootId: string): Set<string> {
  const ids = new Set<string>([rootId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const node of components) {
      if (node.parentId && ids.has(node.parentId) && !ids.has(node.id)) {
        ids.add(node.id);
        grew = true;
      }
    }
  }
  return ids;
}

export function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
  switch (action.type) {
    case "LOAD":
      return createInitialState(action.components);

    case "ADD_COMPONENT": {
      const siblings = state.components.filter((c) => c.parentId === action.parentId);
      const node: ComponentNode = {
        id: action.newId,
        type: action.componentType,
        parentId: action.parentId,
        order: siblings.length,
        props: {},
        styles: {},
      };
      return {
        ...state,
        ...pushHistory(state),
        components: [...state.components, node],
        selectedId: node.id,
        dirty: true,
        historyLocked: false,
      };
    }

    case "SELECT":
      return { ...state, selectedId: action.id };

    case "REMOVE_SELECTED": {
      if (!state.selectedId) return state;
      const toRemove = descendantIds(state.components, state.selectedId);
      return {
        ...state,
        ...pushHistory(state),
        components: state.components.filter((c) => !toRemove.has(c.id)),
        selectedId: null,
        dirty: true,
        historyLocked: false,
      };
    }

    case "MOVE_SELECTED": {
      if (!state.selectedId) return state;
      const current = state.components.find((c) => c.id === state.selectedId);
      if (!current) return state;
      const siblings = state.components
        .filter((c) => c.parentId === current.parentId)
        .sort((a, b) => a.order - b.order);
      const index = siblings.findIndex((c) => c.id === current.id);
      const swapWith = action.direction === "up" ? index - 1 : index + 1;
      if (swapWith < 0 || swapWith >= siblings.length) return state;

      const a = siblings[index];
      const b = siblings[swapWith];
      const components = state.components.map((c) => {
        if (c.id === a.id) return { ...c, order: b.order };
        if (c.id === b.id) return { ...c, order: a.order };
        return c;
      });
      return { ...state, ...pushHistory(state), components, dirty: true, historyLocked: false };
    }

    case "UPDATE_PROP": {
      const base = state.historyLocked ? {} : pushHistory(state);
      const components = state.components.map((c) =>
        c.id === action.id ? { ...c, [action.scope]: { ...c[action.scope], [action.key]: action.value } } : c
      );
      return { ...state, ...base, components, dirty: true, historyLocked: true };
    }

    case "COMMIT_HISTORY":
      return { ...state, historyLocked: false };

    case "SET_MODE":
      return { ...state, mode: action.mode, selectedId: action.mode === "preview" ? null : state.selectedId };

    case "UNDO": {
      if (state.past.length === 0) return state;
      const previous = state.past[state.past.length - 1];
      return {
        ...state,
        components: previous,
        past: state.past.slice(0, -1),
        future: [state.components, ...state.future].slice(0, MAX_HISTORY),
        selectedId: null,
        dirty: true,
        historyLocked: false,
      };
    }

    case "REDO": {
      if (state.future.length === 0) return state;
      const next = state.future[0];
      return {
        ...state,
        components: next,
        future: state.future.slice(1),
        past: [...state.past, state.components].slice(-MAX_HISTORY),
        selectedId: null,
        dirty: true,
        historyLocked: false,
      };
    }

    case "MARK_SAVED":
      return { ...state, dirty: false };

    default:
      return state;
  }
}

export function childrenOf(components: ComponentNode[], parentId: string | null): ComponentNode[] {
  return components.filter((c) => c.parentId === parentId).sort((a, b) => a.order - b.order);
}
