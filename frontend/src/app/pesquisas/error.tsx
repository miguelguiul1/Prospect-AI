"use client";

import { RouteError } from "@/components/shared/route-error";

export default function PesquisasError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError error={error} reset={reset} title="Não foi possível carregar as pesquisas." />;
}
