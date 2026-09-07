"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { Loader2, Sparkles, Send, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  generateOutreachAction,
  editOutreachAction,
  transitionOutreachAction,
} from "@/app/crm/actions";
import { INITIAL_STATE } from "@/lib/action-types";
import { OUTREACH_CHANNEL_LABEL, OUTREACH_STATUS_LABEL, formatRelativeShort } from "@/lib/format";
import type { ContactSummary, OutreachMessage } from "@/lib/api/types";

function GenerateButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="sm" disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
      {pending ? "Gerando…" : "Gerar sugestão"}
    </Button>
  );
}

function GenerateForm({ opportunityId, contacts }: { opportunityId: string; contacts: ContactSummary[] }) {
  const [state, formAction] = useActionState(generateOutreachAction, INITIAL_STATE);
  const verifiedContacts = contacts.filter((c) => c.validation_status === "verified");

  return (
    <form action={formAction} className="flex flex-wrap items-end gap-2 rounded-lg border border-dashed border-border p-3">
      <input type="hidden" name="opportunityId" value={opportunityId} />
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground" htmlFor="channel">Canal</label>
        <select
          id="channel"
          name="channel"
          defaultValue="email"
          className="h-8 rounded-lg border border-input bg-transparent px-2 text-xs outline-none dark:bg-input/30"
        >
          <option value="email">E-mail</option>
          <option value="whatsapp">WhatsApp</option>
          <option value="other">Outro</option>
        </select>
      </div>
      {verifiedContacts.length > 0 ? (
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground" htmlFor="contactId">Personalizar para</label>
          <select
            id="contactId"
            name="contactId"
            defaultValue=""
            className="h-8 rounded-lg border border-input bg-transparent px-2 text-xs outline-none dark:bg-input/30"
          >
            <option value="">Sem contato específico</option>
            {verifiedContacts.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
      ) : null}
      <GenerateButton />
      {state.status === "error" ? <p className="w-full text-xs text-destructive">{state.message}</p> : null}
      {state.status === "success" ? <p className="w-full text-xs text-emerald-700 dark:text-emerald-400">{state.message}</p> : null}
    </form>
  );
}

function OutreachEditForm({ opportunityId, outreach }: { opportunityId: string; outreach: OutreachMessage }) {
  const [editState, editAction] = useActionState(editOutreachAction, INITIAL_STATE);

  return (
    <form action={editAction} className="flex flex-col gap-2">
      <input type="hidden" name="opportunityId" value={opportunityId} />
      <input type="hidden" name="outreachId" value={outreach.id} />
      <Input name="subject" defaultValue={outreach.subject ?? ""} maxLength={300} placeholder="Assunto" />
      <Textarea name="message" defaultValue={outreach.message ?? ""} maxLength={4000} rows={4} placeholder="Mensagem" />
      <div className="flex items-center justify-between">
        {editState.status === "error" ? <p className="text-xs text-destructive">{editState.message}</p> : <span />}
        <SaveEditButton />
      </div>
    </form>
  );
}

function SaveEditButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" size="sm" variant="secondary" disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : null}
      {pending ? "Salvando…" : "Salvar edição"}
    </Button>
  );
}

function TransitionButtons({ opportunityId, outreach }: { opportunityId: string; outreach: OutreachMessage }) {
  const [, formAction] = useActionState(transitionOutreachAction, INITIAL_STATE);

  return (
    <form action={formAction} className="flex flex-wrap gap-2">
      <input type="hidden" name="opportunityId" value={opportunityId} />
      <input type="hidden" name="outreachId" value={outreach.id} />
      {outreach.status === "draft" ? (
        <ActionSubmit name="action" value="mark_ready" label="Marcar como pronto" icon={<Check className="size-4" />} />
      ) : null}
      {(outreach.status === "draft" || outreach.status === "ready") ? (
        <>
          <ActionSubmit name="action" value="mark_sent" label="Já enviei manualmente" icon={<Send className="size-4" />} />
          <ActionSubmit name="action" value="cancel" label="Cancelar" icon={<X className="size-4" />} variant="ghost" />
        </>
      ) : null}
    </form>
  );
}

function ActionSubmit({ name, value, label, icon, variant }: { name: string; value: string; label: string; icon: React.ReactNode; variant?: "outline" | "ghost" }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" name={name} value={value} size="sm" variant={variant ?? "outline"} disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : icon}
      {label}
    </Button>
  );
}

export function OutreachPanel({
  opportunityId,
  contacts,
  history,
}: {
  opportunityId: string;
  contacts: ContactSummary[];
  history: OutreachMessage[];
}) {
  return (
    <div className="flex flex-col gap-4">
      <GenerateForm opportunityId={opportunityId} contacts={contacts} />

      <ul className="flex flex-col gap-3">
        {history.map((outreach) => (
          <li key={outreach.id} className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{OUTREACH_CHANNEL_LABEL[outreach.channel]}</span>
                <span>·</span>
                <span>{OUTREACH_STATUS_LABEL[outreach.status]}</span>
                <span>·</span>
                <span>{formatRelativeShort(outreach.created_at)}</span>
              </div>
            </div>

            {outreach.status === "draft" || outreach.status === "ready" ? (
              <OutreachEditForm opportunityId={opportunityId} outreach={outreach} />
            ) : (
              <div>
                <p className="text-sm font-medium text-foreground">{outreach.subject}</p>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">{outreach.message}</p>
              </div>
            )}

            {outreach.rationale ? (
              <p className="text-xs italic text-muted-foreground">Por que: {outreach.rationale}</p>
            ) : null}

            <TransitionButtons opportunityId={opportunityId} outreach={outreach} />
          </li>
        ))}
        {history.length === 0 ? <li className="text-sm text-muted-foreground">Nenhuma sugestão gerada ainda.</li> : null}
      </ul>
    </div>
  );
}
