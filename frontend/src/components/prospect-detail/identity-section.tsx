import { SectionCard } from "@/components/shared/section-card";
import { evidenceFieldLabel } from "@/lib/format";
import type { CompanyDetail, EvidenceItem } from "@/lib/api/types";

function evidenceValue(evidence: EvidenceItem[], field: string): string | null {
  return evidence.find((e) => e.field === field && e.value)?.value ?? null;
}

export function IdentitySection({ company }: { company: CompanyDetail }) {
  const address = evidenceValue(company.evidence, "address");
  const phone = evidenceValue(company.evidence, "phone");

  const rows: { label: string; value: string }[] = [
    { label: "Categoria", value: company.category_name ?? "Sem categoria" },
    {
      label: "Região",
      value: company.region_name
        ? company.region_state
          ? `${company.region_name}, ${company.region_state}`
          : company.region_name
        : "Sem região",
    },
    { label: evidenceFieldLabel("address"), value: address ?? "Não observado" },
    { label: evidenceFieldLabel("phone"), value: phone ?? "Não observado" },
    { label: "Company ID", value: company.id },
  ];

  return (
    <SectionCard title="Identidade" description={company.canonical_name}>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label} className="flex flex-col gap-0.5">
            <dt className="text-xs font-medium text-muted-foreground">{row.label}</dt>
            <dd className="text-sm text-foreground break-words">{row.value}</dd>
          </div>
        ))}
      </dl>
    </SectionCard>
  );
}
