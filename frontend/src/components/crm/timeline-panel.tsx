"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { Loader2, CheckCircle2, Circle, StickyNote, ListTodo } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { createActivityAction, completeActivityAction } from "@/app/crm/actions";
import { INITIAL_STATE } from "@/lib/action-types";
import { ACTIVITY_TYPE_LABEL, formatRelativeShort } from "@/lib/format";
import type { ActivityItem, ActivityTypeValue } from "@/lib/api/types";

function AddButton({ pendingLabel }: { pendingLabel: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="sm" disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : null}
      {pending ? pendingLabel : "Adicionar"}
    </Button>
  );
}

function QuickAddForm({ opportunityId }: { opportunityId: string }) {
  const [state, formAction] = useActionState(createActivityAction, INITIAL_STATE);

  return (
    <form action={formAction} className="flex flex-col gap-2 rounded-lg border border-dashed border-border p-3">
      <input type="hidden" name="opportunityId" value={opportunityId} />
      <div className="flex flex-wrap items-center gap-2">
        <select
          name="type"
          defaultValue="note"
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-xs outline-none dark:bg-input/30"
        >
          <option value="note">Nota</option>
          <option value="task">Tarefa</option>
          <option value="call">Ligação</option>
          <option value="meeting">Reunião</option>
        </select>
        <Input name="title" placeholder="Título (opcional)" maxLength={200} className="max-w-[16rem]" />
        <Input name="dueAt" type="date" className="max-w-[10rem]" aria-label="Vencimento (para tarefas)" />
      </div>
      <Textarea name="description" placeholder="Escreva uma nota, o que foi conversado, etc." rows={2} maxLength={4000} />
      <div className="flex items-center justify-between">
        {state.status === "error" ? <p className="text-xs text-destructive">{state.message}</p> : <span />}
        <AddButton pendingLabel="Salvando…" />
      </div>
    </form>
  );
}

function TaskToggle({ opportunityId, activity }: { opportunityId: string; activity: ActivityItem }) {
  const [, formAction] = useActionState(completeActivityAction, INITIAL_STATE);
  const done = activity.status === "done";

  return (
    <form action={formAction}>
      <input type="hidden" name="opportunityId" value={opportunityId} />
      <input type="hidden" name="activityId" value={activity.id} />
      <input type="hidden" name="completed" value={done ? "false" : "true"} />
      <button
        type="submit"
        className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
        aria-label={done ? "Reabrir tarefa" : "Concluir tarefa"}
      >
        {done ? <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" /> : <Circle className="size-4" />}
      </button>
    </form>
  );
}

function TimelineIcon({ type }: { type: ActivityTypeValue }) {
  if (type === "task") return <ListTodo className="size-3.5" />;
  return <StickyNote className="size-3.5" />;
}

export function TimelinePanel({ opportunityId, activities }: { opportunityId: string; activities: ActivityItem[] }) {
  return (
    <div className="flex flex-col gap-4">
      <QuickAddForm opportunityId={opportunityId} />

      <ul className="flex flex-col gap-3">
        {activities.map((activity) => (
          <li key={activity.id} className="flex items-start gap-2.5 rounded-lg border border-border bg-card p-3">
            {activity.type === "task" ? (
              <TaskToggle opportunityId={opportunityId} activity={activity} />
            ) : (
              <span className="mt-0.5 shrink-0 text-muted-foreground">
                <TimelineIcon type={activity.type} />
              </span>
            )}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className={activity.status === "done" ? "text-sm font-medium text-muted-foreground line-through" : "text-sm font-medium text-foreground"}>
                  {activity.title || ACTIVITY_TYPE_LABEL[activity.type]}
                </span>
                <span className="text-xs text-muted-foreground">{formatRelativeShort(activity.created_at)}</span>
                {activity.due_at ? (
                  <span className="text-xs text-muted-foreground">· vence {new Date(activity.due_at).toLocaleDateString("pt-BR")}</span>
                ) : null}
              </div>
              {activity.description ? <p className="mt-0.5 text-sm text-muted-foreground">{activity.description}</p> : null}
            </div>
          </li>
        ))}
        {activities.length === 0 ? <li className="text-sm text-muted-foreground">Nenhuma atividade ainda.</li> : null}
      </ul>
    </div>
  );
}
