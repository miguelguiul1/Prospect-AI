"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { History, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { restoreVersionAction } from "@/app/prototypes/[prototypeId]/actions";

/**
 * Restaura uma versão antiga (Fase 9 / Prompt 12) — nunca chama IA, então
 * nenhum estado de "gerando" além do próprio request HTTP. Em sucesso,
 * volta para o Builder (que recarrega `Prototype.components` já
 * atualizado — a restauração já aconteceu no servidor).
 */
export function RestoreVersionButton({ prototypeId, versionId }: { prototypeId: string; versionId: string }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleRestore() {
    setError(null);
    startTransition(async () => {
      const result = await restoreVersionAction(prototypeId, versionId);
      if (result.status === "error") {
        setError(result.message ?? "Não foi possível restaurar esta versão.");
        return;
      }
      router.push(`/prototypes/${prototypeId}`);
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={handleRestore} disabled={isPending}>
        {isPending ? <Loader2 className="size-4 animate-spin" /> : <History className="size-4" />}
        {isPending ? "Restaurando…" : "Restaurar esta versão"}
      </Button>
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
