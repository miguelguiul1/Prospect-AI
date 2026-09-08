"use client";

import { useState, useTransition } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { refinePrototypeAction } from "@/app/prototypes/[prototypeId]/actions";
import type { BuilderAction } from "@/components/prototype-builder/builder-reducer";

/**
 * Refinamento por linguagem natural (Fase 9 / Prompt 12) — deliberadamente
 * um campo de texto + botão "Aplicar" com estado de carregamento, NÃO um
 * chat com histórico de mensagens (fora de escopo desta fase, ver seção 6
 * do Prompt 12). Em sucesso, despacha `LOAD` para substituir a árvore do
 * Builder pela versão nova sem precisar recarregar a página inteira — o
 * `savePrototypeAction` continua existindo separadamente para edição
 * manual, então um refinamento nunca é confundido com uma edição não
 * salva (por isso `LOAD` também zera `dirty`/histórico: a árvore que
 * volta do refinamento JÁ está persistida como uma `PrototypeVersion`).
 */
export function RefinementBar({
  prototypeId,
  dispatch,
}: {
  prototypeId: string;
  dispatch: (action: BuilderAction) => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[] | null>(null);

  function handleApply() {
    const trimmed = instruction.trim();
    if (!trimmed) return;
    setError(null);
    setWarnings(null);
    startTransition(async () => {
      const result = await refinePrototypeAction(prototypeId, trimmed);
      if (result.status === "error") {
        setError(result.message ?? "Não foi possível aplicar o refinamento.");
        return;
      }
      if (result.components) {
        dispatch({ type: "LOAD", components: result.components });
      }
      setWarnings(result.run?.groundingWarnings ?? null);
      setInstruction("");
    });
  }

  return (
    <div className="flex flex-col gap-2 border-b border-border bg-muted/30 px-4 py-3">
      <div className="flex items-start gap-2">
        <Textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder='Descreva a mudança desejada — ex.: "deixa mais premium e destaca o botão de WhatsApp"'
          aria-label="Instrução de refinamento"
          disabled={isPending}
          className="min-h-9 flex-1 bg-background"
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              handleApply();
            }
          }}
        />
        <Button size="sm" onClick={handleApply} disabled={isPending || !instruction.trim()}>
          {isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {isPending ? "Aplicando…" : "Aplicar"}
        </Button>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {warnings && warnings.length > 0 ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <p className="font-medium">Revisar antes de usar:</p>
          <ul className="mt-1 list-inside list-disc">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
