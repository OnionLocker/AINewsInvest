import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp, AlertTriangle, Target, Lightbulb, Crosshair, TrendingDown, BarChart3, Activity, Eye, Users, Calendar } from "lucide-react";

function fmt(v, decimals = 2) {
  if (v == null || isNaN(Number(v))) return "--";
  return Number(v).toFixed(decimals);
}

function pctFromEntry(tp, entry, isShort = false) {
  if (!tp || !entry || entry === 0) return null;
  if (isShort) return (((entry - tp) / entry) * 100).toFixed(1);
  return (((tp - entry) / entry) * 100).toFixed(1);
}

function ConfidenceBar({ value }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const color = v >= 70 ? "#16A34A" : v >= 50 ? "#2563EB" : v >= 35 ? "#D97706" : "#DC2626";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-base font-semibold text-secondary">{"\u7f6e\u4fe1\u5ea6"} {v}%</span>
      <span className="inline-block h-2.5 w-28 overflow-hidden rounded-full bg-surface-3">
        <span className="block h-full rounded-full" style={{ width: `${v}%`, background: color }} />
      </span>
    </span>
  );
}

function ActionArrow({ action, direction }) {
  const map = {
    buy:        { label: "\u4e70\u5165", color: "#16A34A" },
    strong_buy: { label: "\u79ef\u6781\u4e70\u5165", color: "#16A34A" },
    hold:       { label: "\u89c2\u671b", color: "#2563EB" },
    avoid:      { label: "\u56de\u907f", color: "#DC2626" },
    short:      { label: "\u505a\u7a7a", color: "#9333EA" },
  };
  const a = (action || "").toLowerCase();
  const isShort = direction === "short" || a === "short";
  const info = isShort ? map.short : (map[a] || map.hold);
  return (
    <span className="text-lg font-extrabold" style={{ color: info.color }}>
      --&gt;{info.label}
    </span>
  );
}

function QualityTierBadge({ tier }) {
  const map = {
    high:   { label: "\u9ad8\u4fe1\u5fc3", color: "#16A34A", bg: "rgba(22,163,74,0.07)" },
    medium: { label: "\u4e2d\u7b49",     color: "#2563EB", bg: "rgba(37,99,235,0.07)" },
    low:    { label: "\u89c2\u671b",     color: "#D97706", bg: "rgba(217,119,6,0.07)" },
  };
  const info = map[tier];
  if (!info) return null;
  return (
    <span
      className="rounded-full px-3 py-1 text-sm font-bold"
      style={{ color: info.color, background: info.bg }}
    >
      {info.label}
    </span>
  );
}

function MarketCapTierBadge({ tier }) {
  // Shows market-cap tier so users can see scale context (mega vs mid vs small).
  // Colors intentionally muted to avoid competing with the quality-tier badge.
  const map = {
    large: { label: "\u5927\u76d8", color: "#0F172A", bg: "rgba(15,23,42,0.06)",  title: "\u5e02\u503c \u2265 $50B \u7684\u5927\u76d8/\u5de8\u76d8\u80a1" },
    mid:   { label: "\u4e2d\u76d8", color: "#334155", bg: "rgba(51,65,85,0.06)",  title: "\u5e02\u503c $10B\u2013$50B \u7684\u4e2d\u5e02\u503c\u80a1" },
    small: { label: "\u5c0f\u76d8", color: "#7C2D12", bg: "rgba(124,45,18,0.07)", title: "\u5e02\u503c $2B\u2013$10B \u7684\u5c0f\u5e02\u503c\u80a1" },
  };
  const info = map[tier];
  if (!info) return null;
  return (
    <span
      className="rounded-full px-2.5 py-0.5 text-xs font-semibold"
      style={{ color: info.color, background: info.bg }}
      title={info.title}
    >
      {info.label}
    </span>
  );
}

function ThemeTag({ text }) {
  return (
    <span className="inline-flex items-center gap-1 text-sm font-medium text-secondary">
      <span className="h-1.5 w-1.5 rounded-full bg-surface-3" />
      {text}
    </span>
  );
}

function looksMojibake(text) {
  if (!text) return false;
  return /[\uFFFD\u00C3\u00E6\u00E7\u00E9\u00E8\u00EA\u00EB\u00EE\u00EF\u00F4\u00F6\u00FB\u00FC\u00FF\u2019\u20AC]|[\u95BA\u7F01\u95C1\u951F\u5A75\u70B4]/.test(String(text));
}

function PriceBar({ sl, entry, tp, isShort }) {
  if (!sl || !entry || !tp) return null;
  if (isShort) {
    if (tp >= entry) return null;
    const range = sl - tp;
    if (range <= 0) return null;
    const entryPct = Math.max(12, Math.min(88, ((sl - entry) / range) * 100));
    return (
      <div className="mt-3 flex h-9 w-full overflow-hidden rounded text-sm font-bold">
        <div className="flex items-center justify-center text-up"
          style={{ width: `${Math.max(10, 100 - entryPct - 20)}%`, background: "#16A34A" + "12" }}>
          TP {fmt(tp)}
        </div>
        <div className="flex items-center justify-center text-primary"
          style={{ width: `${Math.max(8, entryPct - 20)}%`, background: "#9333EA" + "10" }}>
          {"\u5165\u573a"} {fmt(entry)}
        </div>
        <div className="flex items-center justify-center text-down"
          style={{ flex: 1, background: "#DC2626" + "12" }}>
          SL {fmt(sl)}
        </div>
      </div>
    );
  }
  if (sl >= tp) return null;
  const range = tp - sl;
  const entryPct = Math.max(12, Math.min(88, ((entry - sl) / range) * 100));
  return (
    <div className="mt-3 flex h-9 w-full overflow-hidden rounded text-sm font-bold">
      <div className="flex items-center justify-center text-down"
        style={{ width: `${entryPct}%`, background: "#DC2626" + "12" }}>
        SL {fmt(sl)}
      </div>
      <div className="flex items-center justify-center text-primary"
        style={{ width: "1px", background: "#E8E2DA" }}>
      </div>
      <div className="flex items-center justify-center text-primary"
        style={{ width: `${Math.max(8, 100 - entryPct - 40)}%`, background: "#2563EB" + "10" }}>
        {"\u5165\u573a"} {fmt(entry)}
      </div>
      <div className="flex items-center justify-center text-up"
        style={{ flex: 1, background: "#16A34A" + "12" }}>
        TP {fmt(tp)}
      </div>
    </div>
  );
}

function TradingPlanGrid({ item, currencySymbol, isShort }) {
  const entry = item.entry_price;
  const tp3Auto = item.take_profit_3 || (item.take_profit_2 && entry
    ? (isShort
        ? entry - (entry - item.take_profit_2) * 1.5
        : entry + (item.take_profit_2 - entry) * 1.5)
    : item.take_profit && entry
      ? (isShort
          ? entry - (entry - item.take_profit) * 2
          : entry + (item.take_profit - entry) * 2)
      : null);
  const pctTP1 = pctFromEntry(item.take_profit, entry, isShort);
  const pctTP2 = pctFromEntry(item.take_profit_2, entry, isShort);
  const pctTP3 = pctFromEntry(tp3Auto, entry, isShort);

  const dirLabel = isShort ? "\u505a\u7a7a\u8ba1\u5212" : "\u4ea4\u6613\u8ba1\u5212";
  const dirColor = isShort ? "#9333EA" : undefined;
  const entryLabel = isShort ? "\u505a\u7a7a\u5165\u573a" : "\u5165\u573a\u4ef7\u4f4d";
  const slLabel = isShort ? "\u6b62\u635f\u4ef7\u4f4d(\u4e0a\u65b9)" : "\u6b62\u635f\u4ef7\u4f4d";
  const addLabel = isShort ? "\u52a0\u4ed3\u4ef7\u4f4d(\u4e0a\u65b9)" : "\u52a0\u4ed3\u4ef7\u4f4d";

  return (
    <div className="mt-4 rounded-xl border border-border bg-white p-5">
      <div className="mb-4 flex items-center gap-2">
        {isShort ? <TrendingDown size={16} style={{ color: "#9333EA" }} /> : <Target size={16} className="text-brand" />}
        <span className="text-base font-medium text-primary" style={dirColor ? { color: dirColor } : undefined}>{dirLabel}</span>
        <span className="rounded border border-border bg-white px-2.5 py-0.5 text-sm font-semibold text-secondary">
          {"\u5efa\u8bae\u6301\u4ed3"} {item.holding_days || 3} {"\u5929"}
        </span>
        {isShort && (
          <span className="rounded border border-[#9333EA]/20 bg-[#9333EA]/10 px-2.5 py-0.5 text-sm font-bold text-[#9333EA]">SHORT</span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className={`rounded-xl border p-4 text-center ${isShort ? "border-[#9333EA]/20 bg-[#9333EA]/10" : "border-brand/20 bg-brand-light"}`}>
          <div className={`text-base font-bold ${isShort ? "text-[#9333EA]" : "text-brand"}`}>{entryLabel}</div>
          <div className="mt-2 text-4xl font-semibold text-primary tabular-nums">{fmt(entry)}</div>
          <div className="mt-1 text-sm font-medium text-secondary">{isShort ? "\u9650\u4ef7\u5356\u51fa" : "\u9650\u4ef7\u6302\u5355"}</div>
        </div>
        <div className="rounded-xl border border-down/20 bg-down/10 p-4 text-center">
          <div className="text-base font-bold text-down">{slLabel}</div>
          <div className="mt-2 text-4xl font-semibold text-down tabular-nums">{fmt(item.stop_loss)}</div>
        </div>
        <div className="rounded-xl border border-[#D97706]/20 bg-[#D97706]/10 p-4 text-center">
          <div className="text-base font-bold text-[#D97706]">{addLabel}</div>
          <div className="mt-2 text-4xl font-semibold text-[#D97706] tabular-nums">{fmt(item.entry_2)}</div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        {[
          { label: "TP1 \u4fdd\u5b88", val: item.take_profit, pct: pctTP1 },
          { label: "TP2 \u6807\u51c6", val: item.take_profit_2, pct: pctTP2 },
          { label: "TP3 \u6fc0\u8fdb", val: tp3Auto, pct: pctTP3 },
        ].map((tp) => (
          <div key={tp.label} className="rounded-xl border border-up/20 bg-up/10 p-4 text-center">
            <div className="text-base font-bold text-up">{tp.label}</div>
            <div className="mt-2 text-4xl font-semibold text-primary tabular-nums">{fmt(tp.val)}</div>
            {tp.pct && <div className="mt-1 text-base font-bold text-up">{isShort ? "" : "+"}{tp.pct}%</div>}
          </div>
        ))}
      </div>
      <PriceBar sl={item.stop_loss} entry={entry} tp={item.take_profit} isShort={isShort} />
      {item.trailing_activation_price > 0 && item.trailing_distance_pct > 0 && (
        <div className="mt-3 rounded-xl border border-accent/20 bg-accent/10 p-4">
          <div className="mb-2 flex items-center gap-2 text-base font-bold text-accent">
            <Activity size={14} />
            {"\u8ffd\u8e2a\u6b62\u635f\u7b56\u7565"}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-sm text-secondary">{"\u6fc0\u6d3b\u4ef7\u4f4d: "}</span>
              <span className="text-base font-semibold text-accent tabular-nums">
                {currencySymbol}{fmt(item.trailing_activation_price)}
              </span>
              {entry > 0 && item.take_profit > 0 && (
                <span className="ml-1 text-sm text-tertiary">
                  {isShort
                    ? `(\u76c8\u5229\u8fbe${Math.round(((entry - item.trailing_activation_price) / (entry - item.take_profit)) * 100)}%)`
                    : `(\u76c8\u5229\u8fbe${Math.round(((item.trailing_activation_price - entry) / (item.take_profit - entry)) * 100)}%)`}
                </span>
              )}
            </div>
            <div>
              <span className="text-sm text-secondary">{"\u56de\u64a4\u4fdd\u62a4: "}</span>
              <span className="text-base font-semibold text-accent">
                {(item.trailing_distance_pct * 100).toFixed(0)}%
              </span>
              <span className="ml-1 text-sm text-tertiary">
                {"\u4ece\u6700\u4f18\u4ef7\u56de\u64a4\u5373\u6b62\u76c8"}
              </span>
            </div>
          </div>
          <p className="mt-2 text-sm text-accent/60">
            {isShort
              ? "\u80a1\u4ef7\u8dcc\u81f3\u6fc0\u6d3b\u4ef7\u540e\uff0c\u6b62\u635f\u5c06\u968f\u4ef7\u683c\u4e0b\u884c\u81ea\u52a8\u6536\u7d27\uff0c\u9501\u5b9a\u90e8\u5206\u5229\u6da6\u3002"
              : "\u80a1\u4ef7\u6da8\u81f3\u6fc0\u6d3b\u4ef7\u540e\uff0c\u6b62\u635f\u5c06\u968f\u4ef7\u683c\u4e0a\u884c\u81ea\u52a8\u62ac\u5347\uff0c\u9501\u5b9a\u90e8\u5206\u5229\u6da6\u3002"}
          </p>
        </div>
      )}
      {item.position_rationale && (
        <p className="mt-2 flex items-center gap-1 text-sm font-medium text-secondary">
          <BarChart3 size={13} className="text-brand" />
          {"\u4ed3\u4f4d\u5efa\u8bae: "}{item.position_rationale}
        </p>
      )}
      <p className="mt-2 flex items-center gap-1 text-sm font-medium text-secondary">
        <Lightbulb size={13} className="text-[#D97706]" />
        {isShort
          ? "\u505a\u7a7a\u64cd\u4f5c\uff1a\u5728\u5165\u573a\u4ef7\u4f4d\u5356\u51fa\uff0c\u80a1\u4ef7\u4e0b\u8dcc\u81f3TP\u65f6\u4e70\u5165\u5e73\u4ed3\u83b7\u5229\uff0c\u4e0a\u6da8\u81f3SL\u65f6\u4e70\u5165\u6b62\u635f\u3002"
          : "\u5165\u573a\u4ef7\u4e3a\u5efa\u8bae\u6302\u9650\u4ef7\u5355\u4f4d\uff0c\u7b49\u56de\u843d\u81f3\u8be5\u4ef7\u4f4d\u81ea\u52a8\u6210\u4ea4\u3002"}
      </p>
    </div>
  );
}

function AnalysisSection({ newsReason, techReason }) {
  return (
    <div className="mt-3 grid gap-3 md:grid-cols-2">
      <div className="rounded-xl border border-border bg-white p-4">
        <div className="mb-2 flex items-center gap-2 text-lg font-bold text-primary">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-secondary" />
          {"\u65b0\u95fb\u9762"}
        </div>
        <p className="text-base font-medium leading-relaxed text-secondary">{newsReason && newsReason.trim() ? newsReason : "\u6682\u65e0\u65b0\u95fb\u5206\u6790"}</p>
      </div>
      <div className="rounded-xl border border-border bg-white p-4">
        <div className="mb-2 flex items-center gap-2 text-lg font-bold text-primary">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-secondary" />
          {"\u6280\u672f\u9762"}
        </div>
        <p className="text-base font-medium leading-relaxed text-secondary">{techReason && techReason.trim() ? techReason : "\u6682\u65e0\u6280\u672f\u5206\u6790"}</p>
      </div>
    </div>
  );
}

const RISK_FLAG_CN = {
  high_valuation: "\u9ad8\u4f30\u503c\u98ce\u9669",
  earnings_miss: "\u8d22\u62a5\u4e0d\u53ca\u9884\u671f",
  earnings_imminent: "\u8d22\u62a5\u53d1\u5e03\u5728\u5373",
  sell_the_fact: "\u5229\u597d\u5151\u73b0\u98ce\u9669",
  unverified_rumor: "\u672a\u8bc1\u5b9e\u4f20\u95fb",
  short_squeeze_risk: "\u8f67\u7a7a\u98ce\u9669",
  high_short_interest: "\u9ad8\u7a7a\u5934\u6301\u4ed3",
  overbought_extended: "\u4e25\u91cd\u8d85\u4e70",
  overbought_mild: "\u8f7b\u5fae\u8d85\u4e70",
  volume_price_divergence: "\u91cf\u4ef7\u80cc\u79bb",
  distribution_risk: "\u7b79\u7801\u6d3e\u53d1\u98ce\u9669",
  consumer_demand_risk: "\u6d88\u8d39\u9700\u6c42\u98ce\u9669",
  regulatory_risk: "\u76d1\u7ba1\u653f\u7b56\u98ce\u9669",
  competition_risk: "\u7ade\u4e89\u52a0\u5267\u98ce\u9669",
  macro_risk: "\u5b8f\u89c2\u7ecf\u6d4e\u98ce\u9669",
  liquidity_risk: "\u6d41\u52a8\u6027\u98ce\u9669",
  sector_rotation: "\u677f\u5757\u8f6e\u52a8\u98ce\u9669",
  geopolitical_risk: "\u5730\u7f18\u653f\u6cbb\u98ce\u9669",
  debt_risk: "\u503a\u52a1\u98ce\u9669",
  dilution_risk: "\u80a1\u6743\u7a00\u91ca\u98ce\u9669",
  insider_selling: "\u5185\u90e8\u4eba\u51cf\u6301",
  technical_breakdown: "\u6280\u672f\u7834\u4f4d\u98ce\u9669",
  supply_chain_risk: "\u4f9b\u5e94\u94fe\u98ce\u9669",
  currency_risk: "\u6c47\u7387\u98ce\u9669",
  margin_pressure: "\u5229\u6da6\u7387\u627f\u538b",
  no_official_catalyst: "\u7f3a\u4e4f\u660e\u786e\u50ac\u5316\u5242",
  no_clear_catalyst: "\u7f3a\u4e4f\u50ac\u5316\u5242",
  turnaround_risk: "\u8f6c\u578b\u98ce\u9669",
  execution_risk: "\u6267\u884c\u98ce\u9669",
  untested_support: "\u652f\u6491\u4f4d\u672a\u7ecf\u9a8c\u8bc1",
  insufficient_signal: "\u4fe1\u53f7\u4e0d\u8db3",
  market_volatility: "\u5e02\u573a\u6ce2\u52a8\u98ce\u9669",
  ai_competition: "AI\u7ade\u4e89\u98ce\u9669",
  antitrust_risk: "\u53cd\u5782\u65ad\u98ce\u9669",
  sell_the_news_risk: "\u5229\u597d\u5151\u73b0\u98ce\u9669",
  cyclical_demand_risk: "\u5468\u671f\u6027\u9700\u6c42\u98ce\u9669",
  run_up_too_fast: "\u6da8\u5e45\u8fc7\u5feb\u98ce\u9669",
  tariff_risk: "\u5173\u7a0e\u98ce\u9669",
  trade_war_risk: "\u8d38\u6613\u6218\u98ce\u9669",
  recession_risk: "\u8870\u9000\u98ce\u9669",
  policy_risk: "\u653f\u7b56\u98ce\u9669",
  guidance_risk: "\u4e1a\u7ee9\u6307\u5f15\u98ce\u9669",
  demand_slowdown: "\u9700\u6c42\u653e\u7f13",
  margin_compression: "\u5229\u6da6\u7387\u538b\u7f29",
  management_risk: "\u7ba1\u7406\u5c42\u98ce\u9669",
  competitive_pressure: "\u7ade\u4e89\u538b\u529b",
  sector_weakness: "\u677f\u5757\u8d70\u5f31",
  momentum_fading: "\u52a8\u80fd\u8870\u51cf",
  valuation_concern: "\u4f30\u503c\u62c5\u5fe7",
  gap_risk: "\u7f3a\u53e3\u98ce\u9669",
  earnings_uncertainty: "\u4e1a\u7ee9\u4e0d\u786e\u5b9a\u6027",
  dividend_cut_risk: "\u524a\u51cf\u80a1\u606f\u98ce\u9669",
  supply_chain_disruption: "\u4f9b\u5e94\u94fe\u4e2d\u65ad",
  weak_fundamentals: "\u57fa\u672c\u9762\u504f\u5f31",
  low_liquidity: "\u6d41\u52a8\u6027\u4f4e",
  high_volatility: "\u9ad8\u6ce2\u52a8\u98ce\u9669",
  resistance_overhead: "\u4e0a\u65b9\u538b\u529b\u4f4d",
  downtrend: "\u4e0b\u884c\u8d8b\u52bf",
  oversold_bounce: "\u8d85\u5356\u53cd\u5f39",
  overbought: "\u8d85\u4e70",
  // v2 tech fallback risk flags (Chinese already, but map for consistency)
  "\u8d85\u4e70\u504f\u79bb": "\u8d85\u4e70\u504f\u79bb",
  "\u91cf\u4ef7\u80cc\u79bb": "\u91cf\u4ef7\u80cc\u79bb",
  "\u9ad8\u6ce2\u52a8": "\u9ad8\u6ce2\u52a8",
  "\u65e5\u5468\u8d8b\u52bf\u77db\u76fe": "\u65e5\u5468\u8d8b\u52bf\u77db\u76fe",
  "\u4e34\u8fd1\u8d22\u62a5": "\u4e34\u8fd1\u8d22\u62a5",
  // v6: new data source risk flags
  "PCR\u53cd\u8f6c\u4fe1\u53f7": "PCR\u53cd\u8f6c\u4fe1\u53f7",
  "\u9ad8\u7ba1\u5927\u5e45\u51cf\u6301": "\u9ad8\u7ba1\u5927\u5e45\u51cf\u6301",
  yield_curve_inversion: "\u6536\u76ca\u7387\u66f2\u7ebf\u5012\u6302",
  yield_inversion_plus_vix: "\u5012\u6302+\u9ad8VIX",
  deep_yield_inversion: "\u6df1\u5ea6\u5012\u6302",
};

const RISK_PHRASE_CN = {
  "no official catalyst": "\u7f3a\u4e4f\u660e\u786e\u50ac\u5316\u5242",
  "turnaround risk": "\u8f6c\u578b\u98ce\u9669",
  "execution risk": "\u6267\u884c\u98ce\u9669",
  "untested support": "\u652f\u6491\u4f4d\u672a\u7ecf\u9a8c\u8bc1",
  "insufficient signal": "\u4fe1\u53f7\u4e0d\u8db3",
  "high volatility": "\u9ad8\u6ce2\u52a8\u98ce\u9669",
  "low liquidity": "\u6d41\u52a8\u6027\u4f4e",
  "valuation concern": "\u4f30\u503c\u62c5\u5fe7",
  "momentum fading": "\u52a8\u80fd\u8870\u51cf",
  "downtrend": "\u4e0b\u884c\u8d8b\u52bf",
  "resistance overhead": "\u4e0a\u65b9\u538b\u529b\u4f4d",
  "weak fundamentals": "\u57fa\u672c\u9762\u504f\u5f31",
  "sector weakness": "\u677f\u5757\u8d70\u5f31",
  "overbought": "\u8d85\u4e70",
  "oversold bounce": "\u8d85\u5356\u53cd\u5f39",
  "gap risk": "\u7f3a\u53e3\u98ce\u9669",
  "earnings uncertainty": "\u4e1a\u7ee9\u4e0d\u786e\u5b9a\u6027",
  "policy risk": "\u653f\u7b56\u98ce\u9669",
  "tariff risk": "\u5173\u7a0e\u98ce\u9669",
  "trade war risk": "\u8d38\u6613\u6218\u98ce\u9669",
  "recession risk": "\u8870\u9000\u98ce\u9669",
  "dividend cut risk": "\u524a\u51cf\u80a1\u606f\u98ce\u9669",
  "guidance risk": "\u4e1a\u7ee9\u6307\u5f15\u98ce\u9669",
  "margin compression": "\u5229\u6da6\u7387\u538b\u7f29",
  "demand slowdown": "\u9700\u6c42\u653e\u7f13",
  "supply chain disruption": "\u4f9b\u5e94\u94fe\u4e2d\u65ad",
  "technical breakdown": "\u6280\u672f\u7834\u4f4d",
  "no clear catalyst": "\u7f3a\u4e4f\u50ac\u5316\u5242",
  "management risk": "\u7ba1\u7406\u5c42\u98ce\u9669",
  "competitive pressure": "\u7ade\u4e89\u538b\u529b",
};

function translateFlag(flag) {
  const trimmed = flag.trim();
  if (RISK_FLAG_CN[trimmed]) return RISK_FLAG_CN[trimmed];
  const lower = trimmed.toLowerCase();
  if (RISK_FLAG_CN[lower]) return RISK_FLAG_CN[lower];
  const asSnake = lower.replace(/\s+/g, "_");
  if (RISK_FLAG_CN[asSnake]) return RISK_FLAG_CN[asSnake];
  if (RISK_PHRASE_CN[lower]) return RISK_PHRASE_CN[lower];
  return trimmed.replace(/_/g, " ");
}

function RiskSection({ riskFlags, riskNote }) {
  let flags = [];
  if (Array.isArray(riskFlags)) {
    flags = riskFlags;
  } else if (typeof riskFlags === "string" && riskFlags) {
    try { flags = JSON.parse(riskFlags); } catch { flags = riskFlags.split(","); }
    if (!Array.isArray(flags)) flags = [flags];
    flags = flags.map((s) => String(s).trim()).filter((s) => s && s !== "[]" && s !== "null");
  }
  if (flags.length === 0 && !riskNote) return null;
  return (
    <div className="mt-3 rounded-xl border border-down/20 bg-down/10 p-4">
      <div className="mb-1.5 flex items-center gap-2 text-base font-bold text-down">
        <AlertTriangle size={16} />
        {"\u98ce\u9669\u63d0\u793a"}
      </div>
      {riskNote && <p className="text-base font-medium leading-relaxed text-down/70">{riskNote}</p>}
      {flags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {flags.map((f, i) => (
            <span key={i} className="rounded border border-down/20 bg-down/10 px-2.5 py-1 text-sm font-bold text-down/90">
              {translateFlag(f)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ScoreDimensionBar({ label, value, icon: Icon, color }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const barColor = v >= 65 ? "#16A34A" : v >= 45 ? "#2563EB" : v >= 30 ? "#D97706" : "#DC2626";
  return (
    <div className="flex items-center gap-2">
      <Icon size={14} style={{ color }} />
      <span className="w-16 text-sm font-semibold text-secondary">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-surface-3 overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${v}%`, background: barColor }} />
      </div>
      <span className="w-8 text-right text-sm font-bold tabular-nums" style={{ color: barColor }}>{v}</span>
    </div>
  );
}

function ScoreDimensions({ item }) {
  const ts = item.tech_score || 0;
  const ns = item.news_score || 0;
  const fs = item.fundamental_score || 0;
  if (!ts && !ns && !fs) return null;
  return (
    <div className="mt-3 rounded-xl border border-border bg-white p-4">
      <div className="mb-3 flex items-center gap-2 text-base font-medium text-primary">
        <BarChart3 size={16} className="text-brand" />
        {"\u591a\u7ef4\u8bc4\u5206"}
      </div>
      <div className="space-y-2.5">
        <ScoreDimensionBar label={"\u6280\u672f\u9762"} value={ts} icon={Activity} color="#2563EB" />
        <ScoreDimensionBar label={"\u57fa\u672c\u9762"} value={fs} icon={BarChart3} color="#D97706" />
        <ScoreDimensionBar label={"\u65b0\u95fb\u9762"} value={ns} icon={Eye} color="#16A34A" />
      </div>
    </div>
  );
}

const INSIDER_SIGNAL_CN = {
  strong_buy: { text: "\u5185\u90e8\u4eba\u5f3a\u70c8\u4e70\u5165", color: "#16A34A" },
  moderate_buy: { text: "\u5185\u90e8\u4eba\u4e70\u5165", color: "#16A34A" },
  strong_sell: { text: "\u5185\u90e8\u4eba\u5f3a\u70c8\u5356\u51fa", color: "#DC2626" },
  moderate_sell: { text: "\u5185\u90e8\u4eba\u5356\u51fa", color: "#DC2626" },
  neutral: { text: "\u5185\u90e8\u4eba\u4e2d\u6027", color: "#8B7E74" },
};

const OPTIONS_SIGNAL_CN = {
  strong_bullish: { text: "\u671f\u6743\u5f3a\u70c8\u770b\u591a", color: "#16A34A" },
  bullish: { text: "\u671f\u6743\u770b\u591a", color: "#16A34A" },
  strong_bearish: { text: "\u671f\u6743\u5f3a\u70c8\u770b\u7a7a", color: "#DC2626" },
  bearish: { text: "\u671f\u6743\u770b\u7a7a", color: "#DC2626" },
  neutral: { text: "\u671f\u6743\u4e2d\u6027", color: "#8B7E74" },
};

function TechIndicators({ item }) {
  const rsi = item.rsi;
  const macdHist = item.macd_histogram;
  const bbPos = item.bollinger_position;
  const obvTrend = item.obv_trend;
  const hasAny = rsi != null || macdHist != null || bbPos != null || (obvTrend && obvTrend !== "");
  if (!hasAny) return null;

  const rsiColor = rsi > 70 ? "#DC2626" : rsi < 30 ? "#16A34A" : "#3D3029";
  const rsiLabel = rsi > 70 ? "\u8d85\u4e70" : rsi < 30 ? "\u8d85\u5356" : "\u4e2d\u6027";
  const macdColor = macdHist > 0 ? "#16A34A" : macdHist < 0 ? "#DC2626" : "#8B7E74";
  const macdLabel = macdHist > 0 ? "\u591a\u5934" : macdHist < 0 ? "\u7a7a\u5934" : "\u4e2d\u6027";
  const bbPct = bbPos != null ? Math.round(bbPos * 100) : null;
  const bbColor = bbPct > 90 ? "#DC2626" : bbPct < 10 ? "#16A34A" : "#3D3029";
  const obvMap = { bullish: { text: "\u591a\u5934", color: "#16A34A" }, bearish: { text: "\u7a7a\u5934", color: "#DC2626" }, neutral: { text: "\u4e2d\u6027", color: "#8B7E74" } };
  const obvInfo = obvMap[obvTrend] || obvMap.neutral;

  return (
    <div className="mt-3 rounded-xl border border-border bg-white p-4">
      <div className="mb-3 flex items-center gap-2 text-base font-medium text-primary">
        <Activity size={16} className="text-brand" />
        {"\u6280\u672f\u6307\u6807"}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {rsi != null && (
          <div className="rounded-xl border border-border bg-surface-3 p-3 text-center">
            <div className="text-xs font-semibold text-secondary">RSI(14)</div>
            <div className="mt-1 text-xl font-bold tabular-nums" style={{ color: rsiColor }}>{fmt(rsi, 1)}</div>
            <div className="mt-0.5 text-xs font-semibold" style={{ color: rsiColor }}>{rsiLabel}</div>
          </div>
        )}
        {macdHist != null && (
          <div className="rounded-xl border border-border bg-surface-3 p-3 text-center">
            <div className="text-xs font-semibold text-secondary">MACD</div>
            <div className="mt-1 text-xl font-bold tabular-nums" style={{ color: macdColor }}>{fmt(macdHist, 4)}</div>
            <div className="mt-0.5 text-xs font-semibold" style={{ color: macdColor }}>{macdLabel}</div>
          </div>
        )}
        {bbPct != null && (
          <div className="rounded-xl border border-border bg-surface-3 p-3 text-center">
            <div className="text-xs font-semibold text-secondary">{"\u5e03\u6797\u5e26"}</div>
            <div className="mt-1 text-xl font-bold tabular-nums" style={{ color: bbColor }}>{bbPct}%</div>
            <div className="mt-0.5 text-xs font-semibold text-secondary">{bbPct > 80 ? "\u8fd1\u4e0a\u8f68" : bbPct < 20 ? "\u8fd1\u4e0b\u8f68" : "\u4e2d\u4f4d"}</div>
          </div>
        )}
        {obvTrend && obvTrend !== "" && (
          <div className="rounded-xl border border-border bg-surface-3 p-3 text-center">
            <div className="text-xs font-semibold text-secondary">OBV</div>
            <div className="mt-1 text-xl font-bold" style={{ color: obvInfo.color }}>{obvInfo.text}</div>
            <div className="mt-0.5 text-xs font-semibold text-secondary">{"\u80fd\u91cf\u6f6e"}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function SignalBadges({ item }) {
  const badges = [];
  const ins = item.insider_signal;
  if (ins && ins !== "" && ins !== "neutral") {
    const info = INSIDER_SIGNAL_CN[ins];
    if (info) badges.push({ text: info.text, color: info.color, icon: Users });
  }
  const opt = item.options_signal;
  if (opt && opt !== "" && opt !== "neutral" && opt !== "unavailable") {
    const info = OPTIONS_SIGNAL_CN[opt];
    if (info) badges.push({ text: info.text, color: info.color, icon: Eye });
  }
  if (item.options_unusual_activity) {
    badges.push({ text: "\u671f\u6743\u5f02\u52a8", color: "#D97706", icon: Activity });
  }
  if (item.options_pc_ratio != null && item.options_pc_ratio > 0) {
    const pcr = Number(item.options_pc_ratio);
    const pcrColor = pcr > 1.2 ? "#DC2626" : pcr < 0.7 ? "#16A34A" : "#8B7E74";
    badges.push({ text: `P/C ${pcr.toFixed(2)}`, color: pcrColor, icon: BarChart3 });
  }
  const eda = item.earnings_days_away;
  const eds = item.earnings_date_str;
  // v11: Widened window (was 0..10) so swing holders see upcoming earnings
  // that will fall within their holding period. Red <= 3 days, amber otherwise.
  if (eda != null && eda >= -1 && eda <= 14) {
    const eColor = eda <= 3 ? "#DC2626" : "#D97706";
    let label;
    if (eda < 0) {
      label = `\u8d22\u62a5\u521a\u516c\u5e03${eds ? ` (${eds})` : ""}`;
    } else if (eda === 0) {
      label = `\u4eca\u65e5\u8d22\u62a5${eds ? ` (${eds})` : ""}`;
    } else {
      label = `${eda}\u5929\u540e\u8d22\u62a5${eds ? ` (${eds})` : ""}`;
    }
    badges.push({ text: label, color: eColor, icon: Calendar });
  }
  if (badges.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {badges.map((b, i) => (
        <span key={i} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-bold"
          style={{ color: b.color, background: b.color + "08", border: `1px solid ${b.color}12` }}>
          <b.icon size={13} />
          {b.text}
        </span>
      ))}
    </div>
  );
}

const SECTOR_CN = {
  Technology: "\u79d1\u6280",
  "Consumer Cyclical": "\u53ef\u9009\u6d88\u8d39",
  "Consumer Defensive": "\u5fc5\u9700\u6d88\u8d39",
  Healthcare: "\u533b\u7597\u4fdd\u5065",
  "Financial Services": "\u91d1\u878d",
  Industrials: "\u5de5\u4e1a",
  Energy: "\u80fd\u6e90",
  "Communication Services": "\u901a\u4fe1\u670d\u52a1",
  "Real Estate": "\u623f\u5730\u4ea7",
  Utilities: "\u516c\u7528\u4e8b\u4e1a",
  "Basic Materials": "\u57fa\u7840\u6750\u6599",
};

export default function RecCard({ item, rank }) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const isUS = item.market === "us_stock";
  const isShort = item.direction === "short";
  const currencySymbol = isUS ? "$ " : "HK$ ";
  const themes = Array.isArray(item.themes) ? item.themes : [];
  const showTrading = item.show_trading_params !== false && item.entry_price;
  const score = item.confidence || item.combined_score || 0;
  const displayName = looksMojibake(item.name) ? item.ticker : item.name;

  const rrRisk = isShort
    ? (item.stop_loss && item.entry_price ? item.stop_loss - item.entry_price : 0)
    : (item.entry_price && item.stop_loss ? item.entry_price - item.stop_loss : 0);
  const rrReward = isShort
    ? (item.entry_price && item.take_profit ? item.entry_price - item.take_profit : 0)
    : (item.take_profit && item.entry_price ? item.take_profit - item.entry_price : 0);
  const rrRatio = rrRisk > 0 ? (rrReward / rrRisk).toFixed(1) : "--";

  const borderHighlight = isShort ? "border-[#9333EA]/30" : "border-border";
  const hoverBorder = isShort ? "hover:border-[#9333EA]/40" : "hover:border-border";

  return (
    <div className={`rounded-2xl border bg-white shadow-md transition-all ${
      expanded ? borderHighlight : `border-border ${hoverBorder}`
    }`}>
      {/* Header */}
      <div className="cursor-pointer px-6 py-5" onClick={() => setExpanded(!expanded)}>
        {/* Row 1 */}
        <div className="flex items-center gap-3">
          <span className={`rounded px-3 py-1 text-base font-extrabold font-mono ${
            isShort ? "border border-[#9333EA]/20 bg-[#9333EA]/10 text-[#9333EA]" : "border border-up/20 bg-up/10 text-up"
          }`}>
            {item.ticker}
          </span>
          {isShort && (
            <span className="rounded border border-[#9333EA]/20 bg-[#9333EA]/10 px-2 py-0.5 text-sm font-bold text-[#9333EA]">
              SHORT
            </span>
          )}
          <QualityTierBadge tier={item.quality_tier} />
          <MarketCapTierBadge tier={item.market_cap_tier} />
          {item.reversal_candidate ? (
            <span
              className="rounded-full border border-[#B45309]/30 bg-[#B45309]/10 px-2.5 py-0.5 text-xs font-bold text-[#B45309]"
              title={"\u5f53\u65e5\u5927\u5e45\u4e0b\u8dcc\uff0c\u5df2\u901a\u8fc7\u8d85\u5356/\u653e\u91cf/\u57fa\u672c\u9762 3 \u91cd\u68c0\u9a8c"}
            >
              {"\u53cd\u8f6c\u5019\u9009"}
            </span>
          ) : null}
          {item.strategy === "swing" ? (
            <span className="rounded-full border border-brand/20 bg-brand/10 px-2.5 py-0.5 text-xs font-bold text-brand">
              {"\u6ce2\u6bb5"} {item.holding_days}{"\u5929"}
            </span>
          ) : (
            <span className="rounded-full border border-up/20 bg-up/10 px-2.5 py-0.5 text-xs font-bold text-up">
              {"\u77ed\u7ebf"} {item.holding_days}{"\u5929"}
            </span>
          )}
          <span className="text-xl font-light text-primary">{displayName}</span>
          {item.sector && item.sector !== "" && (
            <span className="rounded-full border border-brand/20 bg-brand/10 px-2.5 py-0.5 text-xs font-bold text-brand">
              {SECTOR_CN[item.sector] || item.sector}
            </span>
          )}
          {themes.slice(0, 3).map((t, i) => (
            <ThemeTag key={i} text={String(t)} />
          ))}
          <div className="ml-auto flex items-center gap-2">
            <Link
              to={`/analysis?ticker=${item.ticker}&market=${item.market}`}
              onClick={(e) => e.stopPropagation()}
              className="rounded bg-brand px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-brand/90"
            >
              {"\u67e5\u770b\u8be6\u60c5"}
            </Link>
            <button className="text-secondary transition-colors hover:text-primary"
              onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}>
              {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
            </button>
          </div>
        </div>

        {/* Row 2 */}
        <div className="mt-2 flex flex-wrap items-center gap-4">
          <span className="text-4xl font-semibold tabular-nums text-primary">
            {currencySymbol}{fmt(item.price)}
          </span>
          <span className={`text-lg font-bold tabular-nums ${
            (item.change_pct || 0) >= 0 ? "text-up" : "text-down"
          }`}>
            {(item.change_pct || 0) >= 0 ? "+" : ""}{fmt(item.change_pct, 2)}%
          </span>
          <ActionArrow action={item.action || item.direction} direction={item.direction} />
          <ConfidenceBar value={score} />
          {showTrading && (
            <span className="text-base font-semibold text-secondary">
              {"\u98ce\u9669\u56de\u62a5"} 1:{rrRatio}
            </span>
          )}
          {item.position_pct > 0 && (
            <span className={`text-sm font-semibold ${
              item.position_pct >= 6 ? "text-up" :
              item.position_pct >= 4 ? "text-[#D97706]" : "text-down"
            }`}>
              {"\u4ed3\u4f4d"} {item.position_pct}%
            </span>
          )}
        </div>
      </div>

      {/* Expanded Detail */}
      {expanded && (
        <div className="border-t border-border px-5 pb-5">
          {/* Tab Bar */}
          <div className="mt-3 flex border-b border-border">
            {["\u4ea4\u6613\u8ba1\u5212", "\u5206\u6790\u8be6\u60c5", "\u98ce\u9669\u8bc4\u4f30"].map((label, idx) => (
              <button
                key={label}
                onClick={(e) => { e.stopPropagation(); setActiveTab(idx); }}
                className={`px-4 py-2.5 text-base font-medium transition-colors ${
                  activeTab === idx
                    ? "border-b-2 border-brand text-brand"
                    : "text-tertiary hover:text-primary"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Tab 0: Trading Plan */}
          {activeTab === 0 && (
            <div>
              {showTrading && !!item.rr_warning && (
                <div className="mt-3 flex items-center gap-2 rounded-xl border border-[#D97706]/30 bg-[#D97706]/10 px-4 py-3 text-sm font-medium text-[#D97706]">
                  <AlertTriangle size={16} />
                  <span>{"\u98ce\u9669\u6536\u76ca\u6bd4\u504f\u4f4e (R:R < 1.5) \u2014 \u5efa\u8bae\u89c2\u671b\u7b49\u5f85\u66f4\u4f18\u5165\u573a\u70b9\uff0c\u6216\u7f29\u5c0f\u4ed3\u4f4d\u4e25\u683c\u6b62\u635f"}</span>
                </div>
              )}
              {showTrading && <TradingPlanGrid item={item} currencySymbol={currencySymbol} isShort={isShort} />}
              {showTrading && !item.rr_warning && item.quality_tier === "medium" && (
                <div className="mt-3 flex items-center gap-2 rounded-xl border border-[#2563EB]/20 bg-[#2563EB]/10 px-4 py-2 text-sm font-medium text-[#2563EB]">
                  <AlertTriangle size={14} />
                  {"\u4fe1\u53f7\u4e2d\u7b49\u5f3a\u5ea6 \u2014 \u5efa\u8bae\u63a7\u5236\u4ed3\u4f4d\uff0c\u4e25\u683c\u6267\u884c\u6b62\u635f"}
                </div>
              )}
              {!showTrading && (
                <div className="mt-4 rounded-xl border border-[#D97706]/20 bg-[#D97706]/10 p-4 text-base font-medium text-[#D97706]">
                  {item.quality_tier === "low"
                    ? "\u4ec5\u4f9b\u53c2\u8003 \u2014 \u4fe1\u53f7\u8f83\u5f31\uff0c\u5efa\u8bae\u89c2\u671b\uff0c\u6682\u4e0d\u63d0\u4f9b\u4ea4\u6613\u53c2\u6570"
                    : "\u7efc\u5408\u8bc4\u5206\u8f83\u4f4e\uff0c\u6682\u4e0d\u5c55\u793a\u4ea4\u6613\u53c2\u6570"}
                </div>
              )}
              {/* Position suggestion */}
              <div className={`mt-3 rounded-xl border p-4 ${
                isShort ? "border-[#9333EA]/20 bg-[#9333EA]/10" : "border-[#D97706]/20 bg-[#D97706]/10"
              }`}>
                <div className={`mb-1 flex items-center gap-2 text-base font-bold ${
                  isShort ? "text-[#9333EA]" : "text-[#D97706]"
                }`}>
                  <Crosshair size={16} />
                  {isShort ? "\u505a\u7a7a\u4ed3\u4f4d\u5efa\u8bae" : "\u4ed3\u4f4d\u5efa\u8bae"}
                </div>
                <p className={`text-base font-medium ${isShort ? "text-[#9333EA]/70" : "text-[#D97706]/70"}`}>
                  {isShort
                    ? (score >= 70
                      ? "\u505a\u7a7a\u4fe1\u53f7\u8f83\u5f3a\uff0c\u53ef\u9002\u5f53\u52a0\u5927\u7a7a\u5934\u4ed3\u4f4d\uff0c\u4f46\u6ce8\u610f\u8bbe\u7f6e\u4e25\u683c\u6b62\u635f\u3002"
                      : score >= 50
                        ? "\u505a\u7a7a\u4fe1\u53f7\u4e2d\u7b49\uff0c\u5efa\u8bae\u8f7b\u4ed3\u8bd5\u63a2\uff0c\u4e25\u683c\u6b62\u635f\u3002"
                        : "\u505a\u7a7a\u4fe1\u53f7\u504f\u5f31\uff0c\u5efa\u8bae\u89c2\u671b\u4e3a\u4e3b\u3002")
                    : (score >= 70
                      ? "\u8bc4\u5206\u8f83\u9ad8\uff0c\u53ef\u9002\u5f53\u52a0\u5927\u4ed3\u4f4d\uff0c\u5efa\u8bae\u4e94\u6210\u4ed3\u4ee5\u4e0a\u53c2\u4e0e\u3002"
                      : score >= 50
                        ? "\u8bc4\u5206\u4e2d\u7b49\uff0c\u5efa\u8bae\u4e09\u6210\u4ed3\u8bd5\u63a2\u6027\u53c2\u4e0e\uff0c\u8bbe\u597d\u6b62\u635f\u3002"
                        : "\u8bc4\u5206\u504f\u4f4e\uff0c\u5efa\u8bae\u8f7b\u4ed3\u6216\u89c2\u671b\uff0c\u7b49\u5f85\u66f4\u597d\u65f6\u673a\u3002")}
                </p>
              </div>
            </div>
          )}

          {/* Tab 1: Analysis Details */}
          {activeTab === 1 && (
            <div>
              <ScoreDimensions item={item} />
              <TechIndicators item={item} />
              <SignalBadges item={item} />
              <AnalysisSection newsReason={item.news_reason} techReason={item.tech_reason} />
              {(item.llm_reason || item.fundamental_reason || item.valuation_summary) && (
                <div className="mt-3 space-y-3">
                  {item.llm_reason && !looksMojibake(item.llm_reason) && (
                    <div className="rounded-xl border border-brand/20 bg-brand/10 p-4">
                      <div className="mb-2 flex items-center gap-2 text-base font-bold text-brand">
                        <Lightbulb size={16} />
                        AI 综合研判
                      </div>
                      <p className="text-base font-medium leading-relaxed text-secondary whitespace-pre-wrap">{item.llm_reason}</p>
                    </div>
                  )}
                  {item.fundamental_reason && !looksMojibake(item.fundamental_reason) && (
                    <div className="rounded-xl border border-border bg-white p-4">
                      <div className="mb-2 flex items-center gap-2 text-base font-medium text-primary">
                        <BarChart3 size={16} className="text-[#D97706]" />
                        基本面分析
                      </div>
                      <p className="text-base font-medium leading-relaxed text-secondary">{item.fundamental_reason}</p>
                    </div>
                  )}
                  {item.valuation_summary && !looksMojibake(item.valuation_summary) && (
                    <div className="rounded-xl border border-border bg-white p-4">
                      <div className="mb-2 flex items-center gap-2 text-base font-medium text-primary">
                        <Target size={16} className="text-up" />
                        估值摘要
                      </div>
                      <p className="text-base font-medium leading-relaxed text-secondary">{item.valuation_summary}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Risk Assessment */}
          {activeTab === 2 && (
            <div>
              <RiskSection riskFlags={item.risk_flags} riskNote={item.risk_note} />
              {!item.risk_flags && !item.risk_note && (
                <div className="mt-4 rounded-xl border border-border bg-white p-4 text-base font-medium text-secondary">
                  暂无风险提示信息
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
