import { Skeleton } from "@/components/ui/skeleton";

// layout-matching placeholders (screen readers get one "Loading" status)
export const ListSkeleton = ({ rows = 6, testid = "list-skeleton" }) => (
  <div className="divide-y divide-foreground/10" role="status" aria-label="Loading" data-testid={testid}>
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="grid grid-cols-[1fr_auto] sm:grid-cols-[auto_1fr_120px_110px_130px] items-center gap-4 py-4">
        <Skeleton className="h-5 w-5 rounded hidden sm:block" />
        <div className="space-y-2"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-3 w-1/4" /></div>
        <Skeleton className="h-3 w-20 hidden sm:block" />
        <Skeleton className="h-6 w-16 rounded-full" />
        <Skeleton className="h-4 w-20 justify-self-end hidden sm:block" />
      </div>
    ))}
  </div>
);

export const CardsSkeleton = ({ count = 6 }) => (
  <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" role="status" aria-label="Loading" data-testid="cards-skeleton">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="rounded-2xl border border-foreground/10 p-5 space-y-3">
        <Skeleton className="h-5 w-1/2" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-1/3 mt-4" />
      </div>
    ))}
  </div>
);

export const DashboardSkeleton = () => (
  <div className="space-y-10" role="status" aria-label="Loading" data-testid="dashboard-skeleton">
    <div className="space-y-3"><Skeleton className="h-3 w-24" /><Skeleton className="h-12 w-72" /></div>
    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-2xl border border-foreground/10 p-6 space-y-4">
          <Skeleton className="h-3 w-20" /><Skeleton className="h-8 w-32" /><Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
    <ListSkeleton rows={5} testid="dashboard-recent-skeleton" />
  </div>
);

export const EditorSkeleton = () => (
  <div className="-m-6 sm:-m-10 lg:-m-12" role="status" aria-label="Loading document" data-testid="editor-skeleton">
    <div className="px-4 sm:px-8 py-3 flex flex-wrap gap-2 border-b border-foreground/10">
      <Skeleton className="h-9 w-9 rounded-full" /><Skeleton className="h-9 w-24" />
      {[130, 90, 110].map((w) => <Skeleton key={w} className="h-9 rounded-full" style={{ width: w }} />)}
      <Skeleton className="h-9 w-40 rounded-full ml-auto" />
    </div>
    <div className="py-8 flex justify-center bg-foreground/5">
      <div className="bg-background shadow-sm p-12 space-y-6 w-full max-w-[816px] aspect-[1/1.414]">
        <Skeleton className="h-5 w-32" /><Skeleton className="h-16 w-64" />
        <div className="grid grid-cols-3 gap-6">{[0, 1, 2].map((i) => <div key={i} className="space-y-2"><Skeleton className="h-3 w-16" /><Skeleton className="h-4 w-28" /></div>)}</div>
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
      </div>
    </div>
  </div>
);

export const DetailSkeleton = () => (
  <div className="space-y-6" role="status" aria-label="Loading" data-testid="detail-skeleton">
    <Skeleton className="h-3 w-28" /><Skeleton className="h-12 w-80" />
    <div className="grid sm:grid-cols-3 gap-6">{[0, 1, 2].map((i) => <div key={i} className="space-y-2"><Skeleton className="h-3 w-16" /><Skeleton className="h-4 w-32" /></div>)}</div>
    <ListSkeleton rows={4} />
  </div>
);
