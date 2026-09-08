"use client";

import Link from "next/link";
import { ArrowLeft, Undo2, Redo2, Eye, Pencil, Loader2, Check, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { BuilderAction, BuilderState } from "@/components/prototype-builder/builder-reducer";

export function Toolbar({
  prototypeId,
  state,
  dispatch,
  name,
  onNameChange,
  onSave,
  saving,
  dirty,
}: {
  prototypeId: string;
  state: BuilderState;
  dispatch: (action: BuilderAction) => void;
  name: string;
  onNameChange: (name: string) => void;
  onSave: () => void;
  saving: boolean;
  dirty: boolean;
}) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4">
      <Button size="icon" variant="ghost" render={<Link href="/prototypes" aria-label="Voltar para protótipos" />}>
        <ArrowLeft className="size-4" />
      </Button>

      <Input
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        aria-label="Nome do protótipo"
        className="h-8 max-w-64 font-medium"
      />

      <div className="flex items-center gap-1">
        <Button size="icon-sm" variant="ghost" aria-label="Desfazer" disabled={state.past.length === 0} onClick={() => dispatch({ type: "UNDO" })}>
          <Undo2 className="size-3.5" />
        </Button>
        <Button size="icon-sm" variant="ghost" aria-label="Refazer" disabled={state.future.length === 0} onClick={() => dispatch({ type: "REDO" })}>
          <Redo2 className="size-3.5" />
        </Button>
      </div>

      <div className="ml-auto flex items-center gap-2">
        {dirty && !saving ? <span className="text-xs text-muted-foreground">Alterações não salvas</span> : null}

        <Button
          size="sm"
          variant="outline"
          render={<Link href={`/prototypes/${prototypeId}/versions`} />}
        >
          <History className="size-4" />
          Versões
        </Button>

        <Button
          size="sm"
          variant="outline"
          onClick={() => dispatch({ type: "SET_MODE", mode: state.mode === "edit" ? "preview" : "edit" })}
        >
          {state.mode === "edit" ? <Eye className="size-4" /> : <Pencil className="size-4" />}
          {state.mode === "edit" ? "Preview" : "Editar"}
        </Button>

        <Button size="sm" onClick={onSave} disabled={saving || !dirty}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
          {saving ? "Salvando…" : "Salvar"}
        </Button>
      </div>
    </header>
  );
}
