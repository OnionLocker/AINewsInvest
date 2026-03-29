import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp, AlertTriangle, Target, Lightbulb, Crosshair, TrendingDown } from "lucide-react";

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
  const color = v >= 70 ? "#089981" : v >= 50 ? "#2962ff" : v >= 35 ? "#fb8c00" : "#f23645";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-xs text-[#787b86]">{"\u7f6e\u4fe1\u5ea6"} {v}%</span>
      <span className="inline-block h-1.5 w-20 overflow-hidden rounded-full bg-[#2a2e39]">
        <span className="block h-full rounded-full" style={{ width: `${v}%`, background: color }} />
      </span>
    </span>
  );
}

function ActionArrow({ action, direction }) {
  const map = {
    buy:        { label: "\u4e70\u5165", color: "#089981" },
    strong_buy: { label: "\u79ef\u6781\u4e70\u5165", color: "#089981" },
    hold:       { label: "\u89c2\u671b", color: "#2962ff" },
    avoid:      { label: "\u56de\u907f", color: "#f23645" },
    short:      { label: "\u505a\u7a7a", color: "#e040fb" },
  };
  const a = (action || "").toLowerCase();
  const isShort = direction === "short" || a === "short";
  const info = isShort ? map.short : (map[a] || map.hold);
  return (
    <span className="text-sm font-bold" style={{ color: info.color }}>
      --&gt;{info.label}
    </span>
  );
}

function ThemeTag({ text }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-[#787b86]">
      <span className="h-1 w-1 rounded-full bg-[#363a45]" />
      {text}
    </span>
  );
}

function PriceBar({ sl, entry, tp, isShort }) {
  if (!sl || !entry || !tp) return null;
  if (isShort) {
    if (tp >= entry) return null;
    const range = sl - tp;
    if (range <= 0) return null;
    const entryPct = Math.max(12, Math.min(88, ((sl - entry) / range) * 100));
    return (
      <div className="mt-3 flex h-7 w-full overflow-hidden rounded text-[11px] font-bold">
        <div className="flex items-center justify-center text-[#089981]"
          style={{ width: `${Math.max(10, 100 - entryPct - 20)}%`, background: "#089981" + "30" }}>
          TP {fmt(tp)}
        </div>
        <div className="flex items-center justify-center text-[#d1d4dc]"
          style={{ width: `${Math.max(8, entryPct - 20)}%`, background: "#e040fb" + "25" }}>
          {"\u5165\u573a"} {fmt(entry)}
        </div>
        <div className="flex items-center justify-center text-[#f23645]"
          style={{ flex: 1, background: "#f23645" + "30" }}>
          SL {fmt(sl)}
        </div>
      </div>
    );
  }
  if (sl >= tp) return null;
  const range = tp - sl;
  const entryPct = Math.max(12, Math.min(88, ((entry - sl) / range) * 100));
  return (
    <div className="mt-3 flex h-7 w-full overflow-hidden rounded text-[11px] font-bold">
      <div className="flex items-center justify-center text-[#f23645]"
        style={{ width: `${entryPct}%`, background: "#f23645" + "30" }}>
        SL {fmt(sl)}
      </div>
      <div className="flex items-center justify-center text-[#d1d4dc]"
        style={{ width: "1px", background: "#363a45" }}>
      </div>
      <div className="flex items-center justify-center text-[#d1d4dc]"
        style={{ width: `${Math.max(8, 100 - entryPct - 40)}%`, background: "#2962ff" + "25" }}>
        {"\u5165\u573a"} {fmt(entry)}
      </div>
      <div className="flex items-center justify-center text-[#089981]"
        style={{ flex: 1, background: "#089981" + "30" }}>
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
  const dirColor = isShort ? "#e040fb" : undefined;
  const entryLabel = isShort ? "\u505a\u7a7a\u5165\u573a" : "\u5165\u573a\u4ef7\u4f4d";
  const slLabel = isShort ? "\u6b62\u635f\u4ef7\u4f4d(\u4e0a\u65b9)" : "\u6b62\u635f\u4ef7\u4f4d";
  const addLabel = isShort ? "\u52a0\u4ed3\u4ef7\u4f4d(\u4e0a\u65b9)" : "\u52a0\u4ed3\u4ef7\u4f4d";

  return (
    <div className="mt-4 rounded-lg border border-[#2a2e39] bg-[#131722] p-5">
      <div className="mb-4 flex items-center gap-2">
        {isShort ? <TrendingDown size={14} style={{ color: "#e040fb" }} /> : <Target size={14} className="text-brand-500" />}
        <span className="text-sm font-bold text-[#d1d4dc]" style={dirColor ? { color: dirColor } : undefined}>{dirLabel}</span>
        <span className="rounded bg-[#2a2e39] px-2 py-0.5 text-[11px] text-[#787b86]">
          {"\u5efa\u8bae\u6301\u4ed3"} {item.holding_days || 3} {"\u5929"}
        </span>
        {isShort && (
          <span className="rounded bg-[#e040fb]/15 px-2 py-0.5 text-[11px] font-bold text-[#e040fb]">SHORT</span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className={`rounded-lg border p-4 text-center ${isShort ? "border-[#e040fb]/20 bg-[#e040fb]/5" : "border-[#2a2e39] bg-[#1e222d]"}`}>
          <div className={`text-xs ${isShort ? "text-[#e040fb]" : "text-[#2962ff]"}`}>{entryLabel}</div>
          <div className="mt-2 text-2xl font-bold text-[#d1d4dc] tabular-nums">{fmt(entry)}</div>
          <div className="mt-1 text-[10px] text-[#787b86]">{isShort ? "\u9650\u4ef7\u5356\u51fa" : "\u9650\u4ef7\u6302\u5355"}</div>
        </div>
        <div className="rounded-lg border border-[#f23645]/20 bg-[#f23645]/5 p-4 text-center">
          <div className="text-xs text-[#f23645]">{slLabel}</div>
          <div className="mt-2 text-2xl font-bold text-[#f23645] tabular-nums">{fmt(item.stop_loss)}</div>
        </div>
        <div className="rounded-lg border border-[#fb8c00]/20 bg-[#fb8c00]/5 p-4 text-center">
          <div className="text-xs text-[#fb8c00]">{addLabel}</div>
          <div className="mt-2 text-2xl font-bold text-[#fb8c00] tabular-nums">{fmt(item.entry_2)}</div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        {[
          { label: "TP1 \u4fdd\u5b88", val: item.take_profit, pct: pctTP1 },
          { label: "TP2 \u6807\u51c6", val: item.take_profit_2, pct: pctTP2 },
          { label: "TP3 \u6fc0\u8fdb", val: tp3Auto, pct: pctTP3 },
        ].map((tp) => (
          <div key={tp.label} className="rounded-lg border border-[#089981]/20 bg-[#089981]/5 p-4 text-center">
            <div className="text-xs text-[#089981]">{tp.label}</div>
            <div className="mt-2 text-2xl font-bold text-[#d1d4dc] tabular-nums">{fmt(tp.val)}</div>
            {tp.pct && <div className="mt-1 text-xs text-[#089981]">{isShort ? "" : "+"}{tp.pct}%</div>}
          </div>
        ))}
      </div>
      <PriceBar sl={item.stop_loss} entry={entry} tp={item.take_profit} isShort={isShort} />
      <p className="mt-2 flex items-center gap-1 text-[11px] text-[#787b86]">
        <Lightbulb size={11} className="text-[#fb8c00]" />
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
      <div className="rounded-lg border border-[#2a2e39] bg-[#131722] p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#d1d4dc]">
          <span className="h-2 w-2 rounded-full border-2 border-[#787b86]" />
          {"\u65b0\u95fb\u9762"}
        </div>
        <p className="text-xs leading-relaxed text-[#787b86]">{newsReason && newsReason.trim() ? newsReason : "\u6682\u65e0\u65b0\u95fb\u5206\u6790"}</p>
      </div>
      <div className="rounded-lg border border-[#2a2e39] bg-[#131722] p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#d1d4dc]">
          <span className="h-2 w-2 rounded-full border-2 border-[#787b86]" />
          {"\u6280\u672f\u9762"}
        </div>
        <p className="text-xs leading-relaxed text-[#787b86]">{techReason && techReason.trim() ? techReason : "\u6682\u65e0\u6280\u672f\u5206\u6790"}</p>
      </div>
    </div>
  );
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
    <div className="mt-3 rounded-lg border border-[#f23645]/15 bg-[#f23645]/5 p-4">
      <div className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-[#f23645]">
        <AlertTriangle size={14} />
        {"\u98ce\u9669\u63d0\u793a"}
      </div>
      {riskNote && <p className="text-xs leading-relaxed text-[#f23645]/70">{riskNote}</p>}
      {flags.length > 0 && (
        <p className="text-xs text-[#f23645]/70">{flags.join("\uff0c")}</p>
      )}
    </div>
  );
}

export default function RecCard({ item, rank }) {
  const [expanded, setExpanded] = useState(false);
  const isUS = item.market === "us_stock";
  const isShort = item.direction === "short";
  const currencySymbol = isUS ? "$ " : "HK$ ";
  const themes = Array.isArray(item.themes) ? item.themes : [];
  const showTrading = item.show_trading_params !== false && item.entry_price;
  const score = item.confidence || item.combined_score || 0;

  const rrRisk = isShort
    ? (item.stop_loss && item.entry_price ? item.stop_loss - item.entry_price : 0)
    : (item.entry_price && item.stop_loss ? item.entry_price - item.stop_loss : 0);
  const rrReward = isShort
    ? (item.entry_price && item.take_profit ? item.entry_price - item.take_profit : 0)
    : (item.take_profit && item.entry_price ? item.take_profit - item.entry_price : 0);
  const rrRatio = rrRisk > 0 ? (rrReward / rrRisk).toFixed(1) : "--";

  const borderHighlight = isShort ? "border-[#e040fb]/30" : "border-[#363a45]";
  const hoverBorder = isShort ? "hover:border-[#e040fb]/40" : "hover:border-[#363a45]";

  return (
    <div className={`rounded-lg border transition-colors ${
      expanded ? `${borderHighlight} bg-[#1e222d]` : `border-[#2a2e39] bg-[#1e222d] ${hoverBorder}`
    }`}>
      {/* Header */}
      <div className="cursor-pointer px-5 py-4" onClick={() => setExpanded(!expanded)}>
        {/* Row 1 */}
        <div className="flex items-center gap-3">
          <span className={`rounded px-2 py-0.5 text-xs font-bold font-mono ${
            isShort ? "bg-[#e040fb]/15 text-[#e040fb]" : "bg-[#089981]/15 text-[#089981]"
          }`}>
            {item.ticker}
          </span>
          {isShort && (
            <span className="rounded bg-[#e040fb]/20 px-1.5 py-0.5 text-[10px] font-bold text-[#e040fb]">
              SHORT
            </span>
          )}
          <span className="text-lg font-bold text-[#d1d4dc]">{item.name}</span>
          {themes.slice(0, 3).map((t, i) => (
            <ThemeTag key={i} text={String(t)} />
          ))}
          <div className="ml-auto flex items-center gap-2">
            <Link
              to={`/analysis?ticker=${item.ticker}&market=${item.market}`}
              onClick={(e) => e.stopPropagation()}
              className="rounded bg-brand-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-600 transition-colors"
            >
              {"\u67e5\u770b\u8be6\u60c5"}
            </Link>
            <button className="text-[#787b86] hover:text-[#d1d4dc] transition-colors"
              onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}>
              {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
          </div>
        </div>

        {/* Row 2 */}
        <div className="mt-2 flex flex-wrap items-center gap-4">
          <span className="text-2xl font-bold tabular-nums text-[#d1d4dc]">
            {currencySymbol}{fmt(item.price)}
          </span>
          <span className={`text-sm font-bold tabular-nums ${
            (item.change_pct || 0) >= 0 ? "text-[#089981]" : "text-[#f23645]"
          }`}>
            {(item.change_pct || 0) >= 0 ? "+" : ""}{fmt(item.change_pct, 2)}%
          </span>
          <ActionArrow action={item.action || item.direction} direction={item.direction} />
          <ConfidenceBar value={score} />
          {showTrading && (
            <span className="text-xs text-[#787b86]">
              {"\u98ce\u9669\u56de\u62a5"} 1:{rrRatio}
            </span>
          )}
        </div>
      </div>

      {/* Expanded Detail */}
      {expanded && (
        <div className="border-t border-[#2a2e39] px-5 pb-5">
          {showTrading && <TradingPlanGrid item={item} currencySymbol={currencySymbol} isShort={isShort} />}
          {!showTrading && (
            <div className="mt-4 rounded-lg border border-[#363a45] bg-[#131722] p-4 text-xs text-[#787b86]">
              {"\u7efc\u5408\u8bc4\u5206\u8f83\u4f4e\uff0c\u6682\u4e0d\u5c55\u793a\u4ea4\u6613\u53c2\u6570"}
            </div>
          )}
          <AnalysisSection newsReason={item.news_reason} techReason={item.tech_reason} />
          <RiskSection riskFlags={item.risk_flags} riskNote={item.risk_note} />

          {/* Position suggestion */}
          <div className={`mt-3 rounded-lg border p-4 ${
            isShort ? "border-[#e040fb]/15 bg-[#e040fb]/5" : "border-[#fb8c00]/15 bg-[#fb8c00]/5"
          }`}>
            <div className={`mb-1 flex items-center gap-2 text-sm font-semibold ${
              isShort ? "text-[#e040fb]" : "text-[#fb8c00]"
            }`}>
              <Crosshair size={14} />
              {isShort ? "\u505a\u7a7a\u4ed3\u4f4d\u5efa\u8bae" : "\u4ed3\u4f4d\u5efa\u8bae"}
            </div>
            <p className={`text-xs ${isShort ? "text-[#e040fb]/70" : "text-[#fb8c00]/70"}`}>
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
    </div>
  );
}
