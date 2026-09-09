import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ArrowLeft, Download } from "lucide-react";
import { getPrototypeVersion } from "@/lib/api/prototypes";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { RestoreVersionButton } from "@/components/prototype-builder/restore-version-button";
import { VersionPreview } from "@/components/prototype-builder/version-preview";
import { formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ prototypeId: string; versionId: string }>;
}): Promise<Metadata> {
  const { prototypeId, versionId } = await params;
  try {
    const version = await getPrototypeVersion(prototypeId, versionId);
    return { title: `Versão ${version.versionNumber}` };
  } catch {
    return { title: "Versão" };
  }
}

export default async function PrototypeVersionDetailPage({
  params,
}: {
  params: Promise<{ prototypeId: string; versionId: string }>;
}) {
  const { prototypeId, versionId } = await params;

  let version;
  try {
    version = await getPrototypeVersion(prototypeId, versionId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button
            size="icon"
            variant="ghost"
            render={<Link href={`/prototypes/${prototypeId}/versions`} aria-label="Voltar para versões" />}
          >
            <ArrowLeft className="size-4" />
          </Button>
          <div>
            <h1 className="font-heading text-xl font-semibold text-foreground">
              Versão {version.versionNumber} — {version.description}
            </h1>
            <p className="text-sm text-muted-foreground">
              {formatDateTime(version.createdAt)} · {version.components.length} componente
              {version.components.length === 1 ? "" : "s"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            render={
              <a
                href={`/api/prototypes/${prototypeId}/versions/${version.id}/export`}
                download
                aria-label={`Exportar versão ${version.versionNumber} como .zip estático`}
              />
            }
          >
            <Download className="size-4" />
            Exportar
          </Button>
          <RestoreVersionButton prototypeId={prototypeId} versionId={version.id} />
        </div>
      </div>

      <div className="rounded-xl border border-border p-4">
        <VersionPreview components={version.components} />
      </div>
    </div>
  );
}
