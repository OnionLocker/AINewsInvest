export default function Skeleton({ className = "" }) {
  return <div className={`animate-pulse rounded-lg bg-surface-3 ${className}`} />;
}

export function SkeletonRows({ rows = 3, className = "h-10 w-full" }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={className} />
      ))}
    </div>
  );
}
