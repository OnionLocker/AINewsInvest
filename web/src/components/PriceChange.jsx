const sizeClasses = {
  sm: "text-sm",
  lg: "text-base font-semibold",
  xl: "text-lg font-bold",
};

export default function PriceChange({ value, suffix = "%", size = "sm" }) {
  if (value == null) return <span className="text-flat">--</span>;
  const num = Number(value);
  const color = num > 0 ? "text-up" : num < 0 ? "text-down" : "text-flat";
  const sign = num > 0 ? "+" : "";
  return (
    <span className={`font-mono ${sizeClasses[size] || sizeClasses.sm} ${color}`}>
      {sign}
      {num.toFixed(2)}
      {suffix}
    </span>
  );
}
