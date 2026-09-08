"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { Sparkles, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { refinePrototypeAction } from "@/app/prototypes/[prototypeId]/actions";
import type { RefinementMessage } from "@/lib/api/prototypes";
import type { BuilderAction } from "@/components/prototype-builder/builder-reducer";

/**
 * Chat de refinamento (Fase 9 / Prompt 13 — evolução de `RefinementBar`,
 * Prompt 12). Cada pedido vira uma "mensagem" do usuário, e a versão
 * resultante (ou o erro) vira a "resposta" do sistema, com link para ver
 * aquela versão — nunca edição de mensagens antigas, nunca "regenerar
 * esta resposta".
 *
 * **Decisão de escopo (ver `docs/prototype-refinement.md`)**: o histórico
 * aqui é SÓ DE APRESENTAÇÃO — nunca é reenviado à Anthropic como contexto
 * adicional da próxima chamada de refinamento (que continua recebendo só
 * a árvore atual + a nova instrução, exatamente como no Prompt 12).
 * Migrar para "histórico influencia geração" ficaria para uma fase
 * futura, só se o uso real mostrar necessidade.
 *
 * O histórico completo (incluindo tentativas de sessões anteriores) vem
 * do servidor via `initialRefinements`; depois de cada novo pedido, a
 * lista inteira é buscada de novo (`refinePrototypeAction` já devolve o
 * histórico atualizado) em vez de reconstruída manualmente aqui — uma
 * única fonte de verdade para o formato de uma mensagem.
 */
export function RefinementChat({
  prototypeId,
  dispatch,
  initialRefinements,
}: {
  prototypeId: string;
  dispatch: (action: BuilderAction) => void;
  initialRefinements: RefinementMessage[];
}) {
  const [refinements, setRefinements] = useState(initialRefinements);
  const [instruction, setInstruction] = useState("");
  const [pendingInstruction, setPendingInstruction] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleApply() {
    const trimmed = instruction.trim();
    if (!trimmed) return;
    setError(null);
    setPendingInstruction(trimmed);
    setInstruction("");
    startTransition(async () => {
      const result = await refinePrototypeAction(prototypeId, trimmed);
      setPendingInstruction(null);
      if (result.status === "error") {
        setError(result.message ?? "Não foi possível aplicar o refinamento.");
        return;
      }
      if (result.refinements) setRefinements(result.refinements);
      if (result.components) dispatch({ type: "LOAD", components: result.components });
    });
  }

  const hasHistory = refinements.length > 0 || pendingInstruction !== null;

  return (
    <div className="flex flex-col gap-2 border-b border-border bg-muted/30 px-4 py-3">
      {hasHistory ? (
        <ul className="flex max-h-56 flex-col gap-3 overflow-y-auto" aria-label="Histórico de refinamento">
          {refinements.map((r) => (
            <RefinementMessageItem key={r.id} message={r} prototypeId={prototypeId} />
          ))}
          {pendingInstruction !== null ? (
            <li className="flex flex-col items-end gap-1">
              <p className="max-w-[85%] rounded-lg rounded-br-sm bg-primary px-3 py-1.5 text-sm text-primary-foreground">
                {pendingInstruction}
              </p>
              <div className="flex items-center gap-1.5 self-start rounded-lg rounded-bl-sm border border-border bg-background px-3 py-1.5 text-sm text-muted-foreground">
                <Loader2 className="size-3.5 shrink-0 animate-spin" />
                Aplicando…
              </div>
            </li>
          ) : null}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">
          Peça uma mudança em linguagem natural — ex.: &quot;deixa mais premium e destaca o botão de
          WhatsApp&quot;.
        </p>
      )}

      <div className="flex items-start gap-2">
        <Textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Descreva a mudança desejada…"
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
    </div>
  );
}

function RefinementMessageItem({ message, prototypeId }: { message: RefinementMessage; prototypeId: string }) {
  return (
    <li className="flex flex-col items-end gap-1">
      <p className="max-w-[85%] rounded-lg rounded-br-sm bg-primary px-3 py-1.5 text-sm text-primary-foreground">
        {message.instruction}
      </p>

      <div className="flex max-w-[85%] items-center gap-1.5 self-start rounded-lg rounded-bl-sm border border-border bg-background px-3 py-1.5 text-sm">
        {message.status === "succeeded" ? (
          <>
            <CheckCircle2 className="size-3.5 shrink-0 text-emerald-600" />
            <span>
              Versão {message.versionNumber} criada —{" "}
              {message.versionId ? (
                <Link
                  href={`/prototypes/${prototypeId}/versions/${message.versionId}`}
                  className="underline underline-offset-2"
                >
                  ver
                </Link>
              ) : null}
            </span>
          </>
        ) : message.status === "failed" ? (
          <>
            <XCircle className="size-3.5 shrink-0 text-destructive" />
            <span className="text-destructive">{message.errorMessage ?? "Não foi possível aplicar."}</span>
          </>
        ) : (
          <>
            <Loader2 className="size-3.5 shrink-0 animate-spin" />
            <span className="text-muted-foreground">Aplicando…</span>
          </>
        )}
      </div>

      {message.groundingWarnings && message.groundingWarnings.length > 0 ? (
        <div className="max-w-[85%] self-start rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-700 dark:text-amber-400">
          {message.groundingWarnings.join(" ")}
        </div>
      ) : null}
    </li>
  );
}
