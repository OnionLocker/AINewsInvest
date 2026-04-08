export default function Spinner({ size = "md", className = "" }) {
  const s = size === "sm" ? "h-4 w-4" : size === "lg" ? "h-8 w-8" : "h-6 w-6";
  return (
    <div
      className={`animate-spin rounded-full border-2 border-border border-t-brand ${s} ${className}`}
    />
  );
}

export function PageLoader({ text }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-secondary">
      <Spinner size="lg" />
      {text && <p className="mt-4 text-sm">{text}</p>}
    </div>
  );
}
