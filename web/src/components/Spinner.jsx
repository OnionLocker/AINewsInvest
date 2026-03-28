export default function Spinner({ size = "md", className = "" }) {
  const s = size === "sm" ? "h-4 w-4" : size === "lg" ? "h-10 w-10" : "h-6 w-6";
  return (
    <div
      className={`animate-spin rounded-full border-2 border-brand-500 border-t-transparent ${s} ${className}`}
    />
  );
}

export function PageLoader({ text = "加载中..." }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-500">
      <Spinner size="lg" />
      <p className="mt-4 text-sm">{text}</p>
    </div>
  );
}
