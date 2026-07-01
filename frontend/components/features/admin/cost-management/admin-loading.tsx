export function AdminLoading() {
  return (
    <div className="py-8 sm:py-10">
      <div className="h-12 max-w-2xl animate-pulse rounded-xl bg-secondary" />
      <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div
            key={item}
            className="h-32 animate-pulse rounded-2xl border border-border bg-card/70"
          />
        ))}
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="h-80 animate-pulse rounded-[1.5rem] border border-border bg-card/70" />
        <div className="h-80 animate-pulse rounded-[1.5rem] border border-border bg-card/70" />
      </div>
    </div>
  );
}
