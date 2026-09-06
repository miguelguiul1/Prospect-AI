import { Skeleton } from "@/components/ui/skeleton";

export default function PesquisasLoading() {
  return (
    <div className="flex flex-col gap-4" aria-busy aria-live="polite">
      <div className="flex items-center justify-between">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-8 w-36" />
      </div>
      <Skeleton className="h-80 w-full rounded-lg" />
    </div>
  );
}
