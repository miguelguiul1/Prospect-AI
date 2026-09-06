import Link from "next/link";
import { Compass } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <EmptyState
      icon={<Compass className="size-8" />}
      title="Página não encontrada."
      description="Verifique o endereço ou volte para o Dashboard."
      action={<Button render={<Link href="/dashboard" />}>Ir para o Dashboard</Button>}
    />
  );
}
