export default function PriceChange({ value, suffix = "%", size = "sm" }) {
  if (value == null) return <span className="text-tertiary">--</span>;
  const num = Number(value);
  const color = num > 0 ? "text-up" : num < 0 ? "text-down" : "text-secondary";
  const sign = num > 0 ? "+" : "";
  const textSize =
    size === "xl" ? "text-xl font-semibold" :
    size === "lg" ? "text-lg font-semibold" :
    "text-sm";
  return (
    <span className={`font-mono tabular-nums ${textSize} ${color}`}>
      {sign}
      {num.toFixed(2)}
      {suffix}
    </span>
  );
}
