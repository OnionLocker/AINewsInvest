const variants = {
  green: "bg-green-500/15 text-green-400",
  red: "bg-red-500/15 text-red-400",
  blue: "bg-blue-500/15 text-blue-400",
  yellow: "bg-yellow-500/15 text-yellow-400",
  gray: "bg-gray-500/15 text-gray-400",
  brand: "bg-brand-500/15 text-brand-400",
};

export default function Badge({ children, variant = "gray", className = "" }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${variants[variant] || variants.gray} ${className}`}
    >
      {children}
    </span>
  );
}

export function MarketBadge({ market }) {
  const m = market === "us_stock" ? "美股" : market === "hk_stock" ? "港股" : market;
  const v = market === "us_stock" ? "blue" : "red";
  return <Badge variant={v}>{m}</Badge>;
}

export function DirectionBadge({ direction }) {
  return (
    <Badge variant={direction === "buy" ? "green" : "red"}>
      {direction === "buy" ? "买入" : "卖出"}
    </Badge>
  );
}

export function StrategyBadge({ strategy }) {
  const label = strategy === "short_term" ? "短线" : "波段";
  const v = strategy === "short_term" ? "yellow" : "brand";
  return <Badge variant={v}>{label}</Badge>;
}
