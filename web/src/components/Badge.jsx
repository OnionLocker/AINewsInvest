const variants = {
  green:  "bg-up/10 text-up border border-up/20",
  red:    "bg-down/10 text-down border border-down/20",
  blue:   "bg-accent/10 text-accent border border-accent/20",
  yellow: "bg-[#D97706]/10 text-[#D97706] border border-[#D97706]/20",
  gray:   "bg-surface-2 text-secondary border border-border",
  brand:  "bg-brand-light text-brand border border-brand/20",
  purple: "bg-[#9333EA]/10 text-[#9333EA] border border-[#9333EA]/20",
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
  const m = market === "us_stock" ? "\u7F8E\u80A1" : market === "hk_stock" ? "\u6E2F\u80A1" : market;
  const v = market === "us_stock" ? "blue" : "yellow";
  return <Badge variant={v}>{m}</Badge>;
}

export function DirectionBadge({ direction }) {
  if (direction === "short") {
    return <Badge variant="purple">\u505A\u7A7A</Badge>;
  }
  return (
    <Badge variant={direction === "buy" ? "green" : "red"}>
      {direction === "buy" ? "\u4E70\u5165" : "\u5356\u51FA"}
    </Badge>
  );
}

export function StrategyBadge({ strategy }) {
  const label = strategy === "short_term" ? "\u77ED\u7EBF" : "\u6CE2\u6BB5";
  const v = strategy === "short_term" ? "yellow" : "brand";
  return <Badge variant={v}>{label}</Badge>;
}
