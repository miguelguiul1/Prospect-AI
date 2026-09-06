"use client";

import { AlertCircle, RotateCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/**
 * Estado de erro compreensível para o usuário final — nunca expõe stack
 * trace ou mensagem de driver/exceção crua (a mensagem já chega tratada
 * de `lib/api/client.ts`). O detalhe técnico completo já foi registrado
 * no console do servidor Next.js antes de chegar aqui.
 */
export function ErrorState({
  title = "Não foi possível carregar os dados.",
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <Alert variant="destructive" className="my-4">
      <AlertCircle className="size-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="flex flex-col gap-3">
        <span>{message ?? "Tente novamente em instantes."}</span>
        {onRetry ? (
          <Button size="sm" variant="outline" onClick={onRetry} className="w-fit">
            <RotateCw className="size-3.5" />
            Tentar novamente
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
