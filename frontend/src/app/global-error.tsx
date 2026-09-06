"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[global-error]", error);
  }, [error]);

  return (
    <html lang="pt-BR">
      <body className="flex min-h-screen flex-col items-center justify-center gap-4 bg-white p-6 text-center text-neutral-900">
        <h1 className="text-lg font-semibold">O Prospect AI encontrou um erro inesperado.</h1>
        <p className="max-w-sm text-sm text-neutral-600">Tente novamente em instantes.</p>
        <button
          onClick={reset}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white"
        >
          Tentar novamente
        </button>
      </body>
    </html>
  );
}
