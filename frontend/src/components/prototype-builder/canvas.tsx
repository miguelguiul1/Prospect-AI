"use client";

import { cn } from "@/lib/utils";
import { definitionFor } from "@/lib/prototype/component-registry";
import { childrenOf, type BuilderAction, type BuilderState } from "@/components/prototype-builder/builder-reducer";
import { NodeLeafContent, containerClassName, containerStyle } from "@/components/prototype-builder/node-renderer";
import type { ComponentNode } from "@/lib/prototype/types";
import { EmptyState } from "@/components/shared/empty-state";
import { LayoutTemplate } from "lucide-react";

function CanvasNode({
  node,
  components,
  selectedId,
  mode,
  dispatch,
}: {
  node: ComponentNode;
  components: ComponentNode[];
  selectedId: string | null;
  mode: "edit" | "preview";
  dispatch: (action: BuilderAction) => void;
}) {
  const def = definitionFor(node.type);
  const isSelected = selectedId === node.id;
  const children = childrenOf(components, node.id);

  const content = def?.acceptsChildren ? (
    <div className={cn(containerClassName(node.type), "min-h-10 gap-2")} style={containerStyle(node)}>
      {children.length === 0 ? (
        mode === "edit" ? (
          <span className="text-xs text-muted-foreground/70 italic">Vazio — selecione este container e adicione um componente</span>
        ) : null
      ) : (
        children.map((child) => (
          <CanvasNode key={child.id} node={child} components={components} selectedId={selectedId} mode={mode} dispatch={dispatch} />
        ))
      )}
    </div>
  ) : (
    <NodeLeafContent node={node} />
  );

  if (mode === "preview") return content;

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      aria-label={`Selecionar componente ${def?.label ?? node.type}`}
      onClick={(e) => {
        e.stopPropagation();
        dispatch({ type: "SELECT", id: node.id });
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.stopPropagation();
          dispatch({ type: "SELECT", id: node.id });
        }
      }}
      className={cn(
        "relative rounded-sm outline-offset-2 focus-visible:outline-none",
        isSelected ? "outline outline-2 outline-primary" : "outline outline-1 outline-transparent hover:outline-primary/40"
      )}
    >
      {isSelected && (
        <span className="absolute -top-5 left-0 z-10 rounded bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground">
          {def?.label ?? node.type}
        </span>
      )}
      {content}
    </div>
  );
}

export function Canvas({ state, dispatch }: { state: BuilderState; dispatch: (action: BuilderAction) => void }) {
  const roots = childrenOf(state.components, null);

  return (
    <div
      onClick={() => dispatch({ type: "SELECT", id: null })}
      className="min-h-full w-full rounded-lg border border-dashed border-border bg-background p-6"
      data-testid="canvas"
    >
      {roots.length === 0 ? (
        <EmptyState
          icon={<LayoutTemplate className="size-8" />}
          title="O canvas está vazio."
          description="Adicione um componente pela lista à esquerda para começar."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {roots.map((root) => (
            <CanvasNode key={root.id} node={root} components={state.components} selectedId={state.selectedId} mode={state.mode} dispatch={dispatch} />
          ))}
        </div>
      )}
    </div>
  );
}
