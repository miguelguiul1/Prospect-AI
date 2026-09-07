"use client";

import { useActionState, useRef } from "react";
import { changeStageAction } from "@/app/crm/actions";
import { INITIAL_STATE } from "@/lib/action-types";
import type { PipelineStage } from "@/lib/api/types";

/**
 * Controle explícito de mudança de etapa — nunca drag-and-drop (Prompt 11,
 * seção 15.3: nenhuma biblioteca de arrastar está instalada no projeto;
 * priorizamos estabilidade a um recurso visual que exigiria uma dependência
 * nova). Um `<select>` nativo garante que o valor chega ao FormData sem
 * nenhum componente adicional — envia sozinho ao mudar de opção.
 */
export function StageSelect({
  opportunityId,
  stages,
  currentStageKey,
}: {
  opportunityId: string;
  stages: PipelineStage[];
  currentStageKey: string;
}) {
  const [state, formAction] = useActionState(changeStageAction, INITIAL_STATE);
  const formRef = useRef<HTMLFormElement>(null);

  return (
    <form action={formAction} ref={formRef} className="flex flex-col gap-1">
      <input type="hidden" name="opportunityId" value={opportunityId} />
      <select
        name="stageKey"
        defaultValue={currentStageKey}
        onChange={() => formRef.current?.requestSubmit()}
        aria-label="Mudar etapa"
        className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
      >
        {stages.map((stage) => (
          <option key={stage.key} value={stage.key}>
            {stage.name}
          </option>
        ))}
      </select>
      {state.status === "error" ? <p className="text-xs text-destructive">{state.message}</p> : null}
    </form>
  );
}
