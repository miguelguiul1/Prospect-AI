"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/shared/error-state";

/**
 * Usado pelos `error.tsx` de cada rota (convenção do App Router do
 * Next.js). O Next já garante que só a mensagem lançada chega até aqui em
 * produção — nunca um stack trace — mas ainda assim registramos o erro
 * completo no console do navegador/servidor para depuração.
 */
export function RouteError({
  error,
  reset,
  title,
}: {
  error: Error & { digest?: string };
  reset: () => void;
  title?: string;
}) {
  useEffect(() => {
    console.error("[route-error]", error);
  }, [error]);

  return (
    <div className="py-8">
      <ErrorState title={title} message={error.message} onRetry={reset} />
    </div>
  );
}
