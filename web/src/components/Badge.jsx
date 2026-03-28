const variants = {
  green:  "bg-[#089981]/10 text-[#089981]",
  red:    "bg-[#f23645]/10 text-[#f23645]",
  blue:   "bg-[#2962ff]/10 text-[#2962ff]",
  yellow: "bg-[#fb8c00]/10 text-[#fb8c00]",
  gray:   "bg-[#787b86]/10 text-[#787b86]",
  brand:  "bg-[#2962ff]/10 text-[#2962ff]",
};

export default function Badge({ children, variant = "gray", className = "" }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ${variants[variant] || variants.gray} ${className}`}
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
