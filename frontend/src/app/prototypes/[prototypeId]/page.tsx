import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getPrototype, listRefinements } from "@/lib/api/prototypes";
import { ApiError } from "@/lib/api/client";
import { PrototypeBuilder } from "@/components/prototype-builder/prototype-builder";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ prototypeId: string }>;
}): Promise<Metadata> {
  const { prototypeId } = await params;
  try {
    const prototype = await getPrototype(prototypeId);
    return { title: prototype.name };
  } catch {
    return { title: "Protótipo" };
  }
}

export default async function PrototypeBuilderPage({
  params,
}: {
  params: Promise<{ prototypeId: string }>;
}) {
  const { prototypeId } = await params;

  let prototype;
  let refinements;
  try {
    [prototype, refinements] = await Promise.all([getPrototype(prototypeId), listRefinements(prototypeId)]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <PrototypeBuilder
      prototypeId={prototype.id}
      initialName={prototype.name}
      initialComponents={prototype.components}
      initialRefinements={refinements}
    />
  );
}
