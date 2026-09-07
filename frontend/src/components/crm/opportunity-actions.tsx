"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { Loader2, Trophy, XCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { closeOpportunityAction, reopenOpportunityAction } from "@/app/crm/actions";
import { INITIAL_STATE } from "@/lib/action-types";
import type { OpportunityStatus } from "@/lib/api/types";

function SubmitButton({
  label,
  pendingLabel,
  icon,
  variant,
  name,
  value,
}: {
  label: string;
  pendingLabel: string;
  icon: React.ReactNode;
  variant?: "default" | "outline" | "destructive";
  name?: string;
  value?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" name={name} value={value} size="sm" variant={variant} disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : icon}
      {pending ? pendingLabel : label}
    </Button>
  );
}

export function OpportunityActions({ opportunityId, status }: { opportunityId: string; status: OpportunityStatus }) {
  const [closeState, closeAction] = useActionState(closeOpportunityAction, INITIAL_STATE);
  const [reopenState, reopenFormAction] = useActionState(reopenOpportunityAction, INITIAL_STATE);

  if (status !== "open") {
    return (
      <form action={reopenFormAction} className="flex flex-col items-end gap-1">
        <input type="hidden" name="opportunityId" value={opportunityId} />
        <SubmitButton label="Reabrir" pendingLabel="Reabrindo…" icon={<RotateCcw className="size-4" />} variant="outline" />
        {reopenState.status === "error" ? <p className="text-xs text-destructive">{reopenState.message}</p> : null}
      </form>
    );
  }

  return (
    <form action={closeAction} className="flex flex-col items-end gap-2">
      <input type="hidden" name="opportunityId" value={opportunityId} />
      <Textarea name="reason" placeholder="Motivo (opcional)" rows={1} maxLength={500} className="w-56 text-xs" />
      <div className="flex gap-2">
        <SubmitButton label="Ganhar" pendingLabel="Salvando…" icon={<Trophy className="size-4" />} variant="outline" name="outcome" value="won" />
        <SubmitButton label="Perder" pendingLabel="Salvando…" icon={<XCircle className="size-4" />} variant="outline" name="outcome" value="lost" />
      </div>
      {closeState.status === "error" ? <p className="text-xs text-destructive">{closeState.message}</p> : null}
    </form>
  );
}
