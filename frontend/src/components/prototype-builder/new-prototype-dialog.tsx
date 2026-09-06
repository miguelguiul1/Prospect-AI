"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";
import { Plus, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { createPrototypeAction } from "@/app/prototypes/actions";
import { INITIAL_STATE } from "@/app/prototypes/action-types";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : null}
      {pending ? "Criando…" : "Criar protótipo"}
    </Button>
  );
}

export function NewPrototypeDialog() {
  const [open, setOpen] = useState(false);
  const [state, formAction] = useActionState(createPrototypeAction, INITIAL_STATE);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>
        <Plus className="size-4" />
        Novo protótipo
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Novo protótipo</DialogTitle>
        </DialogHeader>
        <form action={formAction} className="flex flex-col gap-4">
          {state.status === "error" ? (
            <Alert variant="destructive">
              <AlertDescription>{state.message}</AlertDescription>
            </Alert>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="name">Nome *</Label>
            <Input id="name" name="name" placeholder="Ex.: Landing page — Barbearia Central" required maxLength={200} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="description">Descrição / ideia</Label>
            <Textarea id="description" name="description" placeholder="Do que se trata este protótipo?" rows={3} maxLength={2000} />
          </div>
          <DialogFooter>
            <SubmitButton />
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
