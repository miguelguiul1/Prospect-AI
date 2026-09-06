"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { INITIAL_STATE, type ActionState } from "@/app/prospects/[companyId]/action-types";

function SubmitButton({
  label,
  pendingLabel,
  icon,
  variant,
}: {
  label: string;
  pendingLabel: string;
  icon?: React.ReactNode;
  variant?: "default" | "outline" | "secondary";
}) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="sm" variant={variant} disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : icon}
      {pending ? pendingLabel : label}
    </Button>
  );
}

/**
 * Botão que dispara uma Server Action real (nunca simula sucesso no
 * frontend). O estado de erro exibido já vem tratado por
 * `lib/api/client.ts`/`actions.ts` — nunca um stack trace.
 */
export function ActionButton({
  action,
  companyId,
  label,
  pendingLabel,
  icon,
  variant,
  onResult,
}: {
  action: (prev: ActionState, formData: FormData) => Promise<ActionState>;
  companyId: string;
  label: string;
  pendingLabel: string;
  icon?: React.ReactNode;
  variant?: "default" | "outline" | "secondary";
  onResult?: (state: ActionState) => void;
}) {
  const [state, formAction] = useActionState(async (prev: ActionState, formData: FormData) => {
    const result = await action(prev, formData);
    onResult?.(result);
    return result;
  }, INITIAL_STATE);

  return (
    <form action={formAction} className="flex flex-col items-start gap-1.5">
      <input type="hidden" name="companyId" value={companyId} />
      <SubmitButton label={label} pendingLabel={pendingLabel} icon={icon} variant={variant} />
      {state.status === "error" ? (
        <p role="alert" className="max-w-xs text-xs text-destructive">
          {state.message}
        </p>
      ) : null}
      {state.status === "success" ? (
        <p role="status" className="text-xs text-emerald-700 dark:text-emerald-400">
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
