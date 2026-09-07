"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";
import { Loader2, Plus, ShieldCheck, ShieldQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { createContactAction } from "@/app/crm/actions";
import { INITIAL_STATE } from "@/lib/action-types";
import type { ContactSummary } from "@/lib/api/types";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : null}
      {pending ? "Salvando…" : "Adicionar contato"}
    </Button>
  );
}

function AddContactDialog({ opportunityId, companyId }: { opportunityId: string; companyId: string }) {
  const [open, setOpen] = useState(false);
  const [state, formAction] = useActionState(async (prev: typeof INITIAL_STATE, formData: FormData) => {
    const result = await createContactAction(prev, formData);
    if (result.status === "success") setOpen(false);
    return result;
  }, INITIAL_STATE);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <Plus className="size-4" />
        Contato
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Novo contato</DialogTitle>
        </DialogHeader>
        <form action={formAction} className="flex flex-col gap-4">
          <input type="hidden" name="opportunityId" value={opportunityId} />
          <input type="hidden" name="companyId" value={companyId} />
          {state.status === "error" ? (
            <Alert variant="destructive">
              <AlertDescription>{state.message}</AlertDescription>
            </Alert>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="name">Nome *</Label>
            <Input id="name" name="name" required maxLength={200} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">Cargo</Label>
            <Input id="role" name="role" maxLength={120} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">E-mail</Label>
            <Input id="email" name="email" type="email" maxLength={255} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="phone">Telefone</Label>
            <Input id="phone" name="phone" maxLength={50} />
          </div>
          <DialogFooter>
            <SubmitButton />
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ContactsPanel({
  opportunityId,
  companyId,
  contacts,
}: {
  opportunityId: string;
  companyId: string;
  contacts: ContactSummary[];
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {contacts.length === 0 ? "Nenhum contato cadastrado." : `${contacts.length} contato(s)`}
        </p>
        <AddContactDialog opportunityId={opportunityId} companyId={companyId} />
      </div>
      {contacts.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {contacts.map((contact) => (
            <li key={contact.id} className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card p-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{contact.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {[contact.role, contact.email, contact.phone].filter(Boolean).join(" · ") || "Sem detalhes"}
                </p>
              </div>
              {contact.validation_status === "verified" ? (
                <span className="flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-400" title="Contato validado">
                  <ShieldCheck className="size-3.5" /> Validado
                </span>
              ) : (
                <span className="flex items-center gap-1 text-xs text-muted-foreground" title="Ainda não validado — a IA de outreach não usará este nome">
                  <ShieldQuestion className="size-3.5" /> Não validado
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
