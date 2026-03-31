export default function PriceChange({ value, suffix = "%", size = "sm" }) {
  if (value == null) return <span className="text-slate-500">--</span>;
  const num = Number(value);
  const color = num > 0 ? "text-emerald-400" : num < 0 ? "text-rose-400" : "text-slate-500";
  const sign = num > 0 ? "+" : "";
  const textSize = size === "lg" ? "text-sm font-semibold" : "text-xs";
  return (
    <span className={`font-mono tabular-nums ${textSize} ${color}`}>
      {sign}
      {num.toFixed(2)}
      {suffix}
    </span>
  );
}
