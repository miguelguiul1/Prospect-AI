import { Skeleton } from "@/components/ui/skeleton";

export default function PipelineLoading() {
  return (
    <div className="flex flex-col gap-4" aria-busy aria-live="polite">
      <Skeleton className="h-6 w-32" />
      <div className="flex gap-4 overflow-x-auto">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-96 w-72 shrink-0 rounded-lg" />
        ))}
      </div>
    </div>
  );
}
