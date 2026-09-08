"use client";

import { useEffect, useReducer, useState, useTransition } from "react";
import { builderReducer, createInitialState } from "@/components/prototype-builder/builder-reducer";
import { Toolbar } from "@/components/prototype-builder/toolbar";
import { ComponentPalette } from "@/components/prototype-builder/component-palette";
import { Canvas } from "@/components/prototype-builder/canvas";
import { PropertyPanel } from "@/components/prototype-builder/property-panel";
import { RefinementBar } from "@/components/prototype-builder/refinement-bar";
import { savePrototypeAction } from "@/app/prototypes/[prototypeId]/actions";
import type { ComponentNode } from "@/lib/prototype/types";

/**
 * Único Client Component "grande" do Prototype Builder — de propósito: é
 * aqui que o estado de edição (seleção, árvore, undo/redo, modo) precisa
 * viver junto, e span-lo por vários componentes menores só trocaria
 * complexidade de um lugar por prop-drilling em outro. Os componentes
 * filhos (`Canvas`, `ComponentPalette`, `PropertyPanel`, `Toolbar`) são,
 * eles sim, pequenos e de responsabilidade única (seção 11 do Prompt 09).
 */
export function PrototypeBuilder({
  prototypeId,
  initialName,
  initialComponents,
}: {
  prototypeId: string;
  initialName: string;
  initialComponents: ComponentNode[];
}) {
  const [state, dispatch] = useReducer(builderReducer, createInitialState(initialComponents));
  const [name, setName] = useState(initialName);
  const [savedName, setSavedName] = useState(initialName);
  const [isSaving, startSaving] = useTransition();
  const [saveError, setSaveError] = useState<string | null>(null);

  const dirty = state.dirty || name !== savedName;

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const meta = e.ctrlKey || e.metaKey;
      if (!meta) return;
      if (e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        dispatch({ type: "UNDO" });
      } else if ((e.key === "z" && e.shiftKey) || e.key === "y") {
        e.preventDefault();
        dispatch({ type: "REDO" });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (dirty) e.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  function handleSave() {
    setSaveError(null);
    startSaving(async () => {
      const result = await savePrototypeAction(prototypeId, { name, components: state.components });
      if (result.status === "error") {
        setSaveError(result.message ?? "Não foi possível salvar.");
        return;
      }
      setSavedName(name);
      dispatch({ type: "MARK_SAVED" });
    });
  }

  return (
    <div className="-m-4 flex min-h-[80vh] flex-col overflow-hidden rounded-xl border border-border sm:-m-6 lg:-m-8">
      <Toolbar prototypeId={prototypeId} state={state} dispatch={dispatch} name={name} onNameChange={setName} onSave={handleSave} saving={isSaving} dirty={dirty} />

      {saveError ? (
        <p role="alert" className="border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {saveError}
        </p>
      ) : null}

      <RefinementBar prototypeId={prototypeId} dispatch={dispatch} />

      <div className="flex flex-1 flex-col lg:flex-row">
        {state.mode === "edit" ? (
          <>
            <aside className="max-h-[70vh] w-full shrink-0 overflow-y-auto border-b border-border p-4 lg:max-h-none lg:w-64 lg:border-r lg:border-b-0">
              <ComponentPalette state={state} dispatch={dispatch} />
            </aside>
            <div className="min-w-0 flex-1 overflow-y-auto p-6">
              <Canvas state={state} dispatch={dispatch} />
            </div>
            <aside className="max-h-[70vh] w-full shrink-0 overflow-y-auto border-t border-border p-4 lg:max-h-none lg:w-72 lg:border-t-0 lg:border-l">
              <PropertyPanel state={state} dispatch={dispatch} />
            </aside>
          </>
        ) : (
          <div className="min-w-0 flex-1 overflow-y-auto bg-background p-6">
            <Canvas state={state} dispatch={dispatch} />
          </div>
        )}
      </div>

      <footer className="flex h-8 shrink-0 items-center gap-4 border-t border-border bg-muted/40 px-4 text-xs text-muted-foreground">
        <span>{state.components.length} componente{state.components.length === 1 ? "" : "s"}</span>
        <span>{state.mode === "edit" ? "Modo edição" : "Modo preview"}</span>
        {state.selectedId ? <span>Selecionado: {state.selectedId.slice(0, 8)}</span> : null}
      </footer>
    </div>
  );
}
