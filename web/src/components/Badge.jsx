const variants = {
  green:  "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  red:    "bg-rose-500/10 text-rose-400 border border-rose-500/20",
  blue:   "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20",
  yellow: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  gray:   "bg-slate-800 text-slate-400 border border-slate-700",
  brand:  "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20",
  purple: "bg-fuchsia-500/10 text-fuchsia-400 border border-fuchsia-500/20",
};

export default function Badge({ children, variant = "gray", className = "" }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${variants[variant] || variants.gray} ${className}`}
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
