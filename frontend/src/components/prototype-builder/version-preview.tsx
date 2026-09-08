"use client";

import { Canvas } from "@/components/prototype-builder/canvas";
import type { ComponentNode } from "@/lib/prototype/types";

/**
 * Preview somente-leitura de uma `PrototypeVersion` (Fase 9 / Prompt 12,
 * "visualizar uma versão antiga") — reaproveita `Canvas` em modo
 * "preview" com um estado estático (sem `useReducer`, sem histórico de
 * undo/redo: esta tela nunca edita nada, só exibe). `dispatch` é um no-op
 * porque `Canvas` sempre despacha `SELECT` ao clicar fora de um
 * componente, mesmo em modo preview — inofensivo aqui, nunca observado.
 */
export function VersionPreview({ components }: { components: ComponentNode[] }) {
  return (
    <Canvas
      state={{
        components,
        selectedId: null,
        mode: "preview",
        past: [],
        future: [],
        dirty: false,
        historyLocked: false,
      }}
      dispatch={() => {}}
    />
  );
}
