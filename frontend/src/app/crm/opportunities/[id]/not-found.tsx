import Link from "next/link";
import { SearchX } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";

export default function OpportunityNotFound() {
  return (
    <EmptyState
      icon={<SearchX className="size-8" />}
      title="Esta oportunidade não foi encontrada."
      description="Ela pode não existir, ter sido removida, ou pertencer a outro usuário."
      action={<Button render={<Link href="/crm" />}>Voltar para o CRM</Button>}
    />
  );
}
