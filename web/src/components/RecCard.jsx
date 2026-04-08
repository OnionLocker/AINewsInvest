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
  const color = v >= 70 ? "#34d399" : v >= 50 ? "#818cf8" : v >= 35 ? "#f59e0b" : "#fb7185";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-base font-semibold text-neutral-400">{"\u7f6e\u4fe1\u5ea6"} {v}%</span>
      <span className="inline-block h-2.5 w-28 overflow-hidden rounded-full bg-slate-800">
        <span className="block h-full rounded-full" style={{ width: `${v}%`, background: color }} />
      </span>
    </span>
  );
}

function ActionArrow({ action, direction }) {
  const map = {
    buy:        { label: "\u4e70\u5165", color: "#34d399" },
    strong_buy: { label: "\u79ef\u6781\u4e70\u5165", color: "#34d399" },
    hold:       { label: "\u89c2\u671b", color: "#818cf8" },
    avoid:      { label: "\u56de\u907f", color: "#fb7185" },
    short:      { label: "\u505a\u7a7a", color: "#d946ef" },
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

function ThemeTag({ text }) {
  return (
    <span className="inline-flex items-center gap-1 text-sm font-medium text-neutral-400">
      <span className="h-1.5 w-1.5 rounded-full bg-slate-700" />
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
        <div className="flex items-center justify-center text-emerald-400"
          style={{ width: `${Math.max(10, 100 - entryPct - 20)}%`, background: "#34d399" + "30" }}>
          TP {fmt(tp)}
        </div>
        <div className="flex items-center justify-center text-slate-200"
          style={{ width: `${Math.max(8, entryPct - 20)}%`, background: "#d946ef" + "25" }}>
          {"\u5165\u573a"} {fmt(entry)}
        </div>
        <div className="flex items-center justify-center text-rose-400"
          style={{ flex: 1, background: "#fb7185" + "30" }}>
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
      <div className="flex items-center justify-center text-rose-400"
        style={{ width: `${entryPct}%`, background: "#fb7185" + "30" }}>
        SL {fmt(sl)}
      </div>
      <div className="flex items-center justify-center text-slate-200"
        style={{ width: "1px", background: "#475569" }}>
      </div>
      <div className="flex items-center justify-center text-slate-200"
        style={{ width: `${Math.max(8, 100 - entryPct - 40)}%`, background: "#818cf8" + "25" }}>
        {"\u5165\u573a"} {fmt(entry)}
      </div>
      <div className="flex items-center justify-center text-emerald-400"
        style={{ flex: 1, background: "#34d399" + "30" }}>
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
  const dirColor = isShort ? "#d946ef" : undefined;
  const entryLabel = isShort ? "\u505a\u7a7a\u5165\u573a" : "\u5165\u573a\u4ef7\u4f4d";
  const slLabel = isShort ? "\u6b62\u635f\u4ef7\u4f4d(\u4e0a\u65b9)" : "\u6b62\u635f\u4ef7\u4f4d";
  const addLabel = isShort ? "\u52a0\u4ed3\u4ef7\u4f4d(\u4e0a\u65b9)" : "\u52a0\u4ed3\u4ef7\u4f4d";

  return (
    <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.03] p-5">
      <div className="mb-4 flex items-center gap-2">
        {isShort ? <TrendingDown size={16} style={{ color: "#d946ef" }} /> : <Target size={16} className="text-indigo-500" />}
        <span className="text-base font-medium text-white" style={dirColor ? { color: dirColor } : undefined}>{dirLabel}</span>
        <span className="rounded border border-white/[0.06] bg-white/[0.04] px-2.5 py-0.5 text-sm font-semibold text-neutral-400 backdrop-blur-md">
          {"\u5efa\u8bae\u6301\u4ed3"} {item.holding_days || 3} {"\u5929"}
        </span>
        {isShort && (
          <span className="rounded border border-fuchsia-500/20 bg-fuchsia-500/10 px-2.5 py-0.5 text-sm font-bold text-fuchsia-400">SHORT</span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className={`rounded-xl border p-4 text-center ${isShort ? "border-fuchsia-500/20 bg-fuchsia-500/10" : "border-white/[0.06] bg-white/[0.04] backdrop-blur-md"}`}>
          <div className={`text-base font-bold ${isShort ? "text-fuchsia-400" : "text-indigo-400"}`}>{entryLabel}</div>
          <div className="mt-2 text-4xl font-semibold text-slate-200 tabular-nums">{fmt(entry)}</div>
          <div className="mt-1 text-sm font-medium text-neutral-400">{isShort ? "\u9650\u4ef7\u5356\u51fa" : "\u9650\u4ef7\u6302\u5355"}</div>
        </div>
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-4 text-center">
          <div className="text-base font-bold text-rose-400">{slLabel}</div>
          <div className="mt-2 text-4xl font-semibold text-rose-400 tabular-nums">{fmt(item.stop_loss)}</div>
        </div>
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-center">
          <div className="text-base font-bold text-amber-400">{addLabel}</div>
          <div className="mt-2 text-4xl font-semibold text-amber-400 tabular-nums">{fmt(item.entry_2)}</div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        {[
          { label: "TP1 \u4fdd\u5b88", val: item.take_profit, pct: pctTP1 },
          { label: "TP2 \u6807\u51c6", val: item.take_profit_2, pct: pctTP2 },
          { label: "TP3 \u6fc0\u8fdb", val: tp3Auto, pct: pctTP3 },
        ].map((tp) => (
          <div key={tp.label} className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-center">
            <div className="text-base font-bold text-emerald-400">{tp.label}</div>
            <div className="mt-2 text-4xl font-semibold text-slate-200 tabular-nums">{fmt(tp.val)}</div>
            {tp.pct && <div className="mt-1 text-base font-bold text-emerald-400">{isShort ? "" : "+"}{tp.pct}%</div>}
          </div>
        ))}
      </div>
      <PriceBar sl={item.stop_loss} entry={entry} tp={item.take_profit} isShort={isShort} />
      {item.trailing_activation_price > 0 && item.trailing_distance_pct > 0 && (
        <div className="mt-3 rounded-xl border border-sky-500/20 bg-sky-500/10 p-4">
          <div className="mb-2 flex items-center gap-2 text-base font-bold text-sky-400">
            <Activity size={14} />
            {"\u8ffd\u8e2a\u6b62\u635f\u7b56\u7565"}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-sm text-neutral-400">{"\u6fc0\u6d3b\u4ef7\u4f4d: "}</span>
              <span className="text-base font-semibold text-sky-300 tabular-nums">
                {currencySymbol}{fmt(item.trailing_activation_price)}
              </span>
              {entry > 0 && item.take_profit > 0 && (
                <span className="ml-1 text-sm text-neutral-500">
                  {isShort
                    ? `(\u76c8\u5229\u8fbe${Math.round(((entry - item.trailing_activation_price) / (entry - item.take_profit)) * 100)}%)`
                    : `(\u76c8\u5229\u8fbe${Math.round(((item.trailing_activation_price - entry) / (item.take_profit - entry)) * 100)}%)`}
                </span>
              )}
            </div>
            <div>
              <span className="text-sm text-neutral-400">{"\u56de\u64a4\u4fdd\u62a4: "}</span>
              <span className="text-base font-semibold text-sky-300">
                {(item.trailing_distance_pct * 100).toFixed(0)}%
              </span>
              <span className="ml-1 text-sm text-neutral-500">
                {"\u4ece\u6700\u4f18\u4ef7\u56de\u64a4\u5373\u6b62\u76c8"}
              </span>
            </div>
          </div>
          <p className="mt-2 text-sm text-sky-400/60">
            {isShort
              ? "\u80a1\u4ef7\u8dcc\u81f3\u6fc0\u6d3b\u4ef7\u540e\uff0c\u6b62\u635f\u5c06\u968f\u4ef7\u683c\u4e0b\u884c\u81ea\u52a8\u6536\u7d27\uff0c\u9501\u5b9a\u90e8\u5206\u5229\u6da6\u3002"
              : "\u80a1\u4ef7\u6da8\u81f3\u6fc0\u6d3b\u4ef7\u540e\uff0c\u6b62\u635f\u5c06\u968f\u4ef7\u683c\u4e0a\u884c\u81ea\u52a8\u62ac\u5347\uff0c\u9501\u5b9a\u90e8\u5206\u5229\u6da6\u3002"}
          </p>
        </div>
      )}
      {item.position_rationale && (
        <p className="mt-2 flex items-center gap-1 text-sm font-medium text-neutral-400">
          <BarChart3 size={13} className="text-indigo-400" />
          {"\u4ed3\u4f4d\u5efa\u8bae: "}{item.position_rationale}
        </p>
      )}
      <p className="mt-2 flex items-center gap-1 text-sm font-medium text-neutral-400">
        <Lightbulb size={13} className="text-amber-400" />
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
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
        <div className="mb-2 flex items-center gap-2 text-lg font-bold text-white">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-slate-400" />
          {"\u65b0\u95fb\u9762"}
        </div>
        <p className="text-base font-medium leading-relaxed text-neutral-400">{newsReason && newsReason.trim() ? newsReason : "\u6682\u65e0\u65b0\u95fb\u5206\u6790"}</p>
      </div>
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
        <div className="mb-2 flex items-center gap-2 text-lg font-bold text-white">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-slate-400" />
          {"\u6280\u672f\u9762"}
        </div>
        <p className="text-base font-medium leading-relaxed text-neutral-400">{techReason && techReason.trim() ? techReason : "\u6682\u65e0\u6280\u672f\u5206\u6790"}</p>
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
    <div className="mt-3 rounded-xl border border-rose-500/20 bg-rose-500/10 p-4">
      <div className="mb-1.5 flex items-center gap-2 text-base font-bold text-rose-400">
        <AlertTriangle size={16} />
        {"\u98ce\u9669\u63d0\u793a"}
      </div>
      {riskNote && <p className="text-base font-medium leading-relaxed text-rose-400/70">{riskNote}</p>}
      {flags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {flags.map((f, i) => (
            <span key={i} className="rounded border border-rose-500/20 bg-rose-500/10 px-2.5 py-1 text-sm font-bold text-rose-400/90">
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
  const barColor = v >= 65 ? "#34d399" : v >= 45 ? "#818cf8" : v >= 30 ? "#f59e0b" : "#fb7185";
  return (
    <div className="flex items-center gap-2">
      <Icon size={14} style={{ color }} />
      <span className="w-16 text-sm font-semibold text-neutral-400">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-slate-800 overflow-hidden">
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
    <div className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="mb-3 flex items-center gap-2 text-base font-medium text-white">
        <BarChart3 size={16} className="text-indigo-400" />
        {"\u591a\u7ef4\u8bc4\u5206"}
      </div>
      <div className="space-y-2.5">
        <ScoreDimensionBar label={"\u6280\u672f\u9762"} value={ts} icon={Activity} color="#818cf8" />
        <ScoreDimensionBar label={"\u57fa\u672c\u9762"} value={fs} icon={BarChart3} color="#f59e0b" />
        <ScoreDimensionBar label={"\u65b0\u95fb\u9762"} value={ns} icon={Eye} color="#34d399" />
      </div>
    </div>
  );
}

const INSIDER_SIGNAL_CN = {
  strong_buy: { text: "\u5185\u90e8\u4eba\u5f3a\u70c8\u4e70\u5165", color: "#34d399" },
  moderate_buy: { text: "\u5185\u90e8\u4eba\u4e70\u5165", color: "#34d399" },
  strong_sell: { text: "\u5185\u90e8\u4eba\u5f3a\u70c8\u5356\u51fa", color: "#fb7185" },
  moderate_sell: { text: "\u5185\u90e8\u4eba\u5356\u51fa", color: "#fb7185" },
  neutral: { text: "\u5185\u90e8\u4eba\u4e2d\u6027", color: "#94a3b8" },
};

const OPTIONS_SIGNAL_CN = {
  strong_bullish: { text: "\u671f\u6743\u5f3a\u70c8\u770b\u591a", color: "#34d399" },
  bullish: { text: "\u671f\u6743\u770b\u591a", color: "#34d399" },
  strong_bearish: { text: "\u671f\u6743\u5f3a\u70c8\u770b\u7a7a", color: "#fb7185" },
  bearish: { text: "\u671f\u6743\u770b\u7a7a", color: "#fb7185" },
  neutral: { text: "\u671f\u6743\u4e2d\u6027", color: "#94a3b8" },
};

function TechIndicators({ item }) {
  const rsi = item.rsi;
  const macdHist = item.macd_histogram;
  const bbPos = item.bollinger_position;
  const obvTrend = item.obv_trend;
  const hasAny = rsi != null || macdHist != null || bbPos != null || (obvTrend && obvTrend !== "");
  if (!hasAny) return null;

  const rsiColor = rsi > 70 ? "#fb7185" : rsi < 30 ? "#34d399" : "#e2e8f0";
  const rsiLabel = rsi > 70 ? "\u8d85\u4e70" : rsi < 30 ? "\u8d85\u5356" : "\u4e2d\u6027";
  const macdColor = macdHist > 0 ? "#34d399" : macdHist < 0 ? "#fb7185" : "#94a3b8";
  const macdLabel = macdHist > 0 ? "\u591a\u5934" : macdHist < 0 ? "\u7a7a\u5934" : "\u4e2d\u6027";
  const bbPct = bbPos != null ? Math.round(bbPos * 100) : null;
  const bbColor = bbPct > 90 ? "#fb7185" : bbPct < 10 ? "#34d399" : "#e2e8f0";
  const obvMap = { bullish: { text: "\u591a\u5934", color: "#34d399" }, bearish: { text: "\u7a7a\u5934", color: "#fb7185" }, neutral: { text: "\u4e2d\u6027", color: "#94a3b8" } };
  const obvInfo = obvMap[obvTrend] || obvMap.neutral;

  return (
    <div className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="mb-3 flex items-center gap-2 text-base font-medium text-white">
        <Activity size={16} className="text-indigo-400" />
        {"\u6280\u672f\u6307\u6807"}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {rsi != null && (
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.04] p-3 text-center backdrop-blur-md">
            <div className="text-xs font-semibold text-neutral-400">RSI(14)</div>
            <div className="mt-1 text-xl font-bold tabular-nums" style={{ color: rsiColor }}>{fmt(rsi, 1)}</div>
            <div className="mt-0.5 text-xs font-semibold" style={{ color: rsiColor }}>{rsiLabel}</div>
          </div>
        )}
        {macdHist != null && (
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.04] p-3 text-center backdrop-blur-md">
            <div className="text-xs font-semibold text-neutral-400">MACD</div>
            <div className="mt-1 text-xl font-bold tabular-nums" style={{ color: macdColor }}>{fmt(macdHist, 4)}</div>
            <div className="mt-0.5 text-xs font-semibold" style={{ color: macdColor }}>{macdLabel}</div>
          </div>
        )}
        {bbPct != null && (
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.04] p-3 text-center backdrop-blur-md">
            <div className="text-xs font-semibold text-neutral-400">{"\u5e03\u6797\u5e26"}</div>
            <div className="mt-1 text-xl font-bold tabular-nums" style={{ color: bbColor }}>{bbPct}%</div>
            <div className="mt-0.5 text-xs font-semibold text-neutral-400">{bbPct > 80 ? "\u8fd1\u4e0a\u8f68" : bbPct < 20 ? "\u8fd1\u4e0b\u8f68" : "\u4e2d\u4f4d"}</div>
          </div>
        )}
        {obvTrend && obvTrend !== "" && (
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.04] p-3 text-center backdrop-blur-md">
            <div className="text-xs font-semibold text-neutral-400">OBV</div>
            <div className="mt-1 text-xl font-bold" style={{ color: obvInfo.color }}>{obvInfo.text}</div>
            <div className="mt-0.5 text-xs font-semibold text-neutral-400">{"\u80fd\u91cf\u6f6e"}</div>
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
    badges.push({ text: "\u671f\u6743\u5f02\u52a8", color: "#f59e0b", icon: Activity });
  }
  if (item.options_pc_ratio != null && item.options_pc_ratio > 0) {
    const pcr = Number(item.options_pc_ratio);
    const pcrColor = pcr > 1.2 ? "#fb7185" : pcr < 0.7 ? "#34d399" : "#94a3b8";
    badges.push({ text: `P/C ${pcr.toFixed(2)}`, color: pcrColor, icon: BarChart3 });
  }
  const eda = item.earnings_days_away;
  const eds = item.earnings_date_str;
  if (eda != null && eda >= 0 && eda <= 10) {
    const eColor = eda <= 3 ? "#fb7185" : "#f59e0b";
    badges.push({ text: `${eda}\u5929\u540e\u8d22\u62a5${eds ? ` (${eds})` : ""}`, color: eColor, icon: Calendar });
  }
  if (badges.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {badges.map((b, i) => (
        <span key={i} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-bold"
          style={{ color: b.color, background: b.color + "15", border: `1px solid ${b.color}30` }}>
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

  const borderHighlight = isShort ? "border-fuchsia-500/30" : "border-white/[0.08]";
  const hoverBorder = isShort ? "hover:border-fuchsia-500/40" : "hover:border-white/[0.08]";

  return (
    <div className={`rounded-3xl border bg-white/[0.03] shadow-xl backdrop-blur-md transition-all ${
      expanded ? borderHighlight : `border-white/[0.06] ${hoverBorder}`
    }`}>
      {/* Header */}
      <div className="cursor-pointer px-6 py-5" onClick={() => setExpanded(!expanded)}>
        {/* Row 1 */}
        <div className="flex items-center gap-3">
          <span className={`rounded px-3 py-1 text-base font-extrabold font-mono ${
            isShort ? "border border-fuchsia-500/20 bg-fuchsia-500/10 text-fuchsia-400" : "border border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
          }`}>
            {item.ticker}
          </span>
          {isShort && (
            <span className="rounded border border-fuchsia-500/20 bg-fuchsia-500/10 px-2 py-0.5 text-sm font-bold text-fuchsia-400">
              SHORT
            </span>
          )}
          <span className="text-xl font-light text-white">{displayName}</span>
          {item.sector && item.sector !== "" && (
            <span className="rounded-full border border-indigo-500/20 bg-indigo-500/10 px-2.5 py-0.5 text-xs font-bold text-indigo-400">
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
              className="rounded bg-indigo-500 px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-indigo-600"
            >
              {"\u67e5\u770b\u8be6\u60c5"}
            </Link>
            <button className="text-neutral-400 transition-colors hover:text-slate-200"
              onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}>
              {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
            </button>
          </div>
        </div>

        {/* Row 2 */}
        <div className="mt-2 flex flex-wrap items-center gap-4">
          <span className="text-4xl font-semibold tabular-nums text-slate-200">
            {currencySymbol}{fmt(item.price)}
          </span>
          <span className={`text-lg font-bold tabular-nums ${
            (item.change_pct || 0) >= 0 ? "text-emerald-400" : "text-rose-400"
          }`}>
            {(item.change_pct || 0) >= 0 ? "+" : ""}{fmt(item.change_pct, 2)}%
          </span>
          <ActionArrow action={item.action || item.direction} direction={item.direction} />
          <ConfidenceBar value={score} />
          {showTrading && (
            <span className="text-base font-semibold text-neutral-400">
              {"\u98ce\u9669\u56de\u62a5"} 1:{rrRatio}
            </span>
          )}
          {item.position_pct > 0 && (
            <span className={`text-sm font-semibold ${
              item.position_pct >= 6 ? "text-emerald-400" :
              item.position_pct >= 4 ? "text-amber-400" : "text-rose-400"
            }`}>
              {"\u4ed3\u4f4d"} {item.position_pct}%
            </span>
          )}
        </div>
      </div>

      {/* Expanded Detail */}
      {expanded && (
        <div className="border-t border-white/[0.06] px-5 pb-5">
          {/* Tab Bar */}
          <div className="mt-3 flex border-b border-white/[0.06]">
            {["\u4ea4\u6613\u8ba1\u5212", "\u5206\u6790\u8be6\u60c5", "\u98ce\u9669\u8bc4\u4f30"].map((label, idx) => (
              <button
                key={label}
                onClick={(e) => { e.stopPropagation(); setActiveTab(idx); }}
                className={`px-4 py-2.5 text-base font-medium transition-colors ${
                  activeTab === idx
                    ? "border-b-2 border-indigo-400 text-indigo-400"
                    : "text-neutral-500 hover:text-slate-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Tab 0: Trading Plan */}
          {activeTab === 0 && (
            <div>
              {showTrading && <TradingPlanGrid item={item} currencySymbol={currencySymbol} isShort={isShort} />}
              {!showTrading && (
                <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 text-base font-medium text-neutral-400">
                  {"\u7efc\u5408\u8bc4\u5206\u8f83\u4f4e\uff0c\u6682\u4e0d\u5c55\u793a\u4ea4\u6613\u53c2\u6570"}
                </div>
              )}
              {/* Position suggestion */}
              <div className={`mt-3 rounded-xl border p-4 ${
                isShort ? "border-fuchsia-500/20 bg-fuchsia-500/10" : "border-amber-500/20 bg-amber-500/10"
              }`}>
                <div className={`mb-1 flex items-center gap-2 text-base font-bold ${
                  isShort ? "text-fuchsia-400" : "text-amber-400"
                }`}>
                  <Crosshair size={16} />
                  {isShort ? "\u505a\u7a7a\u4ed3\u4f4d\u5efa\u8bae" : "\u4ed3\u4f4d\u5efa\u8bae"}
                </div>
                <p className={`text-base font-medium ${isShort ? "text-fuchsia-400/70" : "text-amber-400/70"}`}>
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
                    <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/10 p-4">
                      <div className="mb-2 flex items-center gap-2 text-base font-bold text-indigo-400">
                        <Lightbulb size={16} />
                        AI 综合研判
                      </div>
                      <p className="text-base font-medium leading-relaxed text-neutral-400 whitespace-pre-wrap">{item.llm_reason}</p>
                    </div>
                  )}
                  {item.fundamental_reason && !looksMojibake(item.fundamental_reason) && (
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
                      <div className="mb-2 flex items-center gap-2 text-base font-medium text-white">
                        <BarChart3 size={16} className="text-amber-400" />
                        基本面分析
                      </div>
                      <p className="text-base font-medium leading-relaxed text-neutral-400">{item.fundamental_reason}</p>
                    </div>
                  )}
                  {item.valuation_summary && !looksMojibake(item.valuation_summary) && (
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
                      <div className="mb-2 flex items-center gap-2 text-base font-medium text-white">
                        <Target size={16} className="text-emerald-400" />
                        估值摘要
                      </div>
                      <p className="text-base font-medium leading-relaxed text-neutral-400">{item.valuation_summary}</p>
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
                <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 text-base font-medium text-neutral-400">
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
