"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { INITIAL_STATE, type ActionState } from "@/lib/action-types";

function SubmitButton({ label, pendingLabel }: { label: string; pendingLabel: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" className="w-full" disabled={pending}>
      {pending ? <Loader2 className="size-4 animate-spin" /> : null}
      {pending ? pendingLabel : label}
    </Button>
  );
}

export function AuthForm({
  mode,
  action,
  nextPath,
}: {
  mode: "login" | "register";
  action: (prev: ActionState, formData: FormData) => Promise<ActionState>;
  nextPath?: string;
}) {
  const [state, formAction] = useActionState(action, INITIAL_STATE);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      {nextPath ? <input type="hidden" name="next" value={nextPath} /> : null}

      {mode === "register" ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="name">Nome</Label>
          <Input id="name" name="name" required maxLength={200} autoComplete="name" />
        </div>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="email">E-mail</Label>
        <Input id="email" name="email" type="email" required maxLength={255} autoComplete="email" />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Senha</Label>
        <Input
          id="password"
          name="password"
          type="password"
          required
          minLength={8}
          maxLength={200}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
        />
      </div>

      {state.status === "error" ? (
        <p role="alert" className="text-sm text-destructive">
          {state.message}
        </p>
      ) : null}

      <SubmitButton
        label={mode === "login" ? "Entrar" : "Criar conta"}
        pendingLabel={mode === "login" ? "Entrando…" : "Criando conta…"}
      />
    </form>
  );
}
