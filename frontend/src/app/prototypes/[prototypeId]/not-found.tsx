import Link from "next/link";
import { SearchX } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";

export default function PrototypeNotFound() {
  return (
    <EmptyState
      icon={<SearchX className="size-8" />}
      title="Este protótipo não foi encontrado."
      description="Ele pode ter sido removido, ou o link está incorreto."
      action={<Button render={<Link href="/prototypes" />}>Voltar para protótipos</Button>}
    />
  );
}
