const variants = {
  green:  "bg-emerald-500/8 text-emerald-400 border border-emerald-500/15",
  red:    "bg-rose-500/8 text-rose-400 border border-rose-500/15",
  blue:   "bg-indigo-500/8 text-indigo-400 border border-indigo-500/15",
  yellow: "bg-amber-500/8 text-amber-400 border border-amber-500/15",
  gray:   "bg-white/[0.04] text-neutral-400 border border-white/[0.06]",
  brand:  "bg-indigo-500/8 text-indigo-400 border border-indigo-500/15",
  purple: "bg-fuchsia-500/8 text-fuchsia-400 border border-fuchsia-500/15",
};

export default function Badge({ children, variant = "gray", className = "" }) {
  return (
    <span
      className={`inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-medium ${variants[variant] || variants.gray} ${className}`}
    >
      {children}
    </span>
  );
}

export function MarketBadge({ market }) {
  const m = market === "us_stock" ? "美股" : market === "hk_stock" ? "港股" : market;
  const v = market === "us_stock" ? "blue" : "yellow";
  return <Badge variant={v}>{m}</Badge>;
}

export function DirectionBadge({ direction }) {
  if (direction === "short") {
    return <Badge variant="purple">做空</Badge>;
  }
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
