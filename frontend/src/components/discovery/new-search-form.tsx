"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { Loader2, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { startSearchAction } from "@/app/pesquisas/nova/actions";
import { INITIAL_STATE } from "@/app/pesquisas/nova/action-types";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
      {pending ? "Iniciando…" : "Iniciar pesquisa"}
    </Button>
  );
}

export function NewSearchForm() {
  const [state, formAction] = useActionState(startSearchAction, INITIAL_STATE);

  return (
    <form action={formAction} className="flex max-w-xl flex-col gap-5">
      {state.status === "error" ? (
        <Alert variant="destructive">
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="space-y-1.5">
        <Label htmlFor="category">Categoria *</Label>
        <Input id="category" name="category" placeholder="Ex.: Hamburguerias" required maxLength={120} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="city">Cidade</Label>
          <Input id="city" name="city" placeholder="Ex.: São Paulo" maxLength={120} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="region">Região/bairro</Label>
          <Input id="region" name="region" placeholder="Ex.: Interlagos" maxLength={255} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="state">Estado</Label>
          <Input id="state" name="state" placeholder="Ex.: SP" maxLength={120} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="country">País</Label>
          <Input id="country" name="country" defaultValue="BR" maxLength={2} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="max_results">Quantidade máxima de resultados</Label>
        <Input id="max_results" name="max_results" type="number" min={1} max={60} defaultValue={20} />
        <p className="text-xs text-muted-foreground">Limite interno de segurança: 60 resultados por pesquisa.</p>
      </div>

      <p className="text-xs text-muted-foreground">
        Fonte: <span className="font-medium text-foreground">Google Places</span> — único provider
        implementado nesta fase.
      </p>

      <div>
        <SubmitButton />
      </div>
    </form>
  );
}
