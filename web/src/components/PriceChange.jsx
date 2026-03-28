export default function PriceChange({ value, suffix = "%", size = "sm" }) {
  if (value == null) return <span className="text-[#787b86]">--</span>;
  const num = Number(value);
  const color = num > 0 ? "text-[#089981]" : num < 0 ? "text-[#f23645]" : "text-[#787b86]";
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
