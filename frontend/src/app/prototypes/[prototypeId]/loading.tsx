import { Skeleton } from "@/components/ui/skeleton";

export default function PrototypeBuilderLoading() {
  return (
    <div className="flex flex-col gap-3" aria-busy aria-live="polite">
      <Skeleton className="h-14 w-full" />
      <div className="flex gap-4">
        <Skeleton className="h-96 w-64" />
        <Skeleton className="h-96 flex-1" />
        <Skeleton className="h-96 w-72" />
      </div>
    </div>
  );
}
