"use client";

import { COMPONENT_LIST, definitionFor, type ComponentDefinition } from "@/lib/prototype/component-registry";
import type { BuilderAction, BuilderState } from "@/components/prototype-builder/builder-reducer";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<ComponentDefinition["category"], string> = {
  layout: "Layout",
  content: "Conteúdo",
  form: "Formulário",
  interface: "Interface",
};

const CATEGORY_ORDER: ComponentDefinition["category"][] = ["layout", "content", "form", "interface"];

function newComponentId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `c_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

/**
 * Sem drag-and-drop nesta fase (seção 6 do Prompt 09 permite: "não é
 * obrigatório um editor visual extremamente avançado — priorize
 * estabilidade"). Clicar em um componente da paleta o adiciona: dentro do
 * container atualmente selecionado (se ele aceitar filhos), ou na raiz do
 * canvas, caso contrário.
 */
export function ComponentPalette({ state, dispatch }: { state: BuilderState; dispatch: (action: BuilderAction) => void }) {
  const selected = state.components.find((c) => c.id === state.selectedId);
  const selectedDef = selected ? definitionFor(selected.type) : undefined;
  const targetParentId = selectedDef?.acceptsChildren ? (selected?.id ?? null) : null;

  return (
    <div className="flex flex-col gap-5" data-testid="component-palette">
      {targetParentId ? (
        <p className="rounded-md bg-accent/60 px-2.5 py-1.5 text-xs text-accent-foreground">
          Novo componente entra dentro de <b>{selectedDef?.label}</b>
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">Novo componente entra no topo do canvas</p>
      )}

      {CATEGORY_ORDER.map((category) => (
        <div key={category}>
          <h4 className="mb-2 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            {CATEGORY_LABEL[category]}
          </h4>
          <div className="grid grid-cols-2 gap-2">
            {COMPONENT_LIST.filter((c) => c.category === category).map((def) => {
              const Icon = def.icon;
              return (
                <button
                  key={def.type}
                  type="button"
                  onClick={() =>
                    dispatch({ type: "ADD_COMPONENT", componentType: def.type, parentId: targetParentId, newId: newComponentId() })
                  }
                  className={cn(
                    "flex flex-col items-center gap-1.5 rounded-md border border-border bg-card px-2 py-3 text-xs text-foreground",
                    "hover:border-primary/50 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  )}
                >
                  <Icon className="size-4" aria-hidden />
                  {def.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
