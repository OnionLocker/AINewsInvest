import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp, AlertTriangle, Target, Lightbulb, Crosshair } from "lucide-react";

function fmt(v, decimals = 2) {
  if (v == null || isNaN(Number(v))) return "--";
  return Number(v).toFixed(decimals);
}

function pctFromEntry(tp, entry) {
  if (!tp || !entry || entry === 0) return null;
  return (((tp - entry) / entry) * 100).toFixed(1);
}

function ConfidenceBar({ value }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const color = v >= 70 ? "#089981" : v >= 50 ? "#2962ff" : v >= 35 ? "#fb8c00" : "#f23645";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-xs text-[#787b86]">置信度 {v}%</span>
      <span className="inline-block h-1.5 w-20 overflow-hidden rounded-full bg-[#2a2e39]">
        <span className="block h-full rounded-full" style={{ width: `${v}%`, background: color }} />
      </span>
    </span>
  );
}

function ActionArrow({ action }) {
  const map = {
    buy:        { label: "买入", color: "#089981" },
    strong_buy: { label: "积极买入", color: "#089981" },
    hold:       { label: "观望", color: "#2962ff" },
    avoid:      { label: "回避", color: "#f23645" },
  };
  const a = (action || "").toLowerCase();
  const info = map[a] || map.hold;
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

function PriceBar({ sl, entry, tp }) {
  if (!sl || !entry || !tp || sl >= tp) return null;
  const range = tp - sl;
  const entryPct = Math.max(12, Math.min(88, ((entry - sl) / range) * 100));
  return (
    <div className="mt-3 flex h-7 w-full overflow-hidden rounded text-[11px] font-bold">
      <div className="flex items-center justify-center text-[#f23645]"
        style={{ width: `${entryPct}%`, background: "#f23645" + "30" }}>
        SL{fmt(sl)}
      </div>
      <div className="flex items-center justify-center text-[#d1d4dc]"
        style={{ width: "1px", background: "#363a45" }}>
      </div>
      <div className="flex items-center justify-center text-[#d1d4dc]"
        style={{ width: `${Math.max(8, 100 - entryPct - 40)}%`, background: "#2962ff" + "25" }}>
        入{fmt(entry)}
      </div>
      <div className="flex items-center justify-center text-[#089981]"
        style={{ flex: 1, background: "#089981" + "30" }}>
        TP {fmt(tp)}
      </div>
    </div>
  );
}

function TradingPlanGrid({ item, currencySymbol }) {
  const entry = item.entry_price;
  const tp3Auto = item.take_profit_3 || (item.take_profit_2 && entry
    ? entry + (item.take_profit_2 - entry) * 1.5
    : item.take_profit && entry
      ? entry + (item.take_profit - entry) * 2
      : null);
  const pctTP1 = pctFromEntry(item.take_profit, entry);
  const pctTP2 = pctFromEntry(item.take_profit_2, entry);
  const pctTP3 = pctFromEntry(tp3Auto, entry);
  return (
    <div className="mt-4 rounded-lg border border-[#2a2e39] bg-[#131722] p-5">
      <div className="mb-4 flex items-center gap-2">
        <Target size={14} className="text-brand-500" />
        <span className="text-sm font-bold text-[#d1d4dc]">交易计划</span>
        <span className="rounded bg-[#2a2e39] px-2 py-0.5 text-[11px] text-[#787b86]">
          建议持仓 {item.holding_days || 3} 天
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-[#2a2e39] bg-[#1e222d] p-4 text-center">
          <div className="text-xs text-[#2962ff]">入场价位</div>
          <div className="mt-2 text-2xl font-bold text-[#d1d4dc] tabular-nums">{fmt(entry)}</div>
          <div className="mt-1 text-[10px] text-[#787b86]">限价挂单</div>
        </div>
        <div className="rounded-lg border border-[#f23645]/20 bg-[#f23645]/5 p-4 text-center">
          <div className="text-xs text-[#f23645]">止损价位</div>
          <div className="mt-2 text-2xl font-bold text-[#f23645] tabular-nums">{fmt(item.stop_loss)}</div>
        </div>
        <div className="rounded-lg border border-[#fb8c00]/20 bg-[#fb8c00]/5 p-4 text-center">
          <div className="text-xs text-[#fb8c00]">加仓价位</div>
          <div className="mt-2 text-2xl font-bold text-[#fb8c00] tabular-nums">{fmt(item.entry_2)}</div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        {[
          { label: "TP1 保守", val: item.take_profit, pct: pctTP1 },
          { label: "TP2 标准", val: item.take_profit_2, pct: pctTP2 },
          { label: "TP3 激进", val: tp3Auto, pct: pctTP3 },
        ].map((tp) => (
          <div key={tp.label} className="rounded-lg border border-[#089981]/20 bg-[#089981]/5 p-4 text-center">
            <div className="text-xs text-[#089981]">{tp.label}</div>
            <div className="mt-2 text-2xl font-bold text-[#d1d4dc] tabular-nums">{fmt(tp.val)}</div>
            {tp.pct && <div className="mt-1 text-xs text-[#089981]">+{tp.pct}%</div>}
          </div>
        ))}
      </div>
      <PriceBar sl={item.stop_loss} entry={entry} tp={item.take_profit} />
      <p className="mt-2 flex items-center gap-1 text-[11px] text-[#787b86]">
        <Lightbulb size={11} className="text-[#fb8c00]" />
        入场价为建议挂限价单位，等回落至该价位自动成交。
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
          新闻面
        </div>
        <p className="text-xs leading-relaxed text-[#787b86]">{newsReason && newsReason.trim() ? newsReason : "暂无新闻分析"}</p>
      </div>
      <div className="rounded-lg border border-[#2a2e39] bg-[#131722] p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#d1d4dc]">
          <span className="h-2 w-2 rounded-full border-2 border-[#787b86]" />
          技术面
        </div>
        <p className="text-xs leading-relaxed text-[#787b86]">{techReason && techReason.trim() ? techReason : "暂无技术分析"}</p>
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
        风险提示
      </div>
      {riskNote && <p className="text-xs leading-relaxed text-[#f23645]/70">{riskNote}</p>}
      {flags.length > 0 && (
        <p className="text-xs text-[#f23645]/70">{flags.join("，")}</p>
      )}
    </div>
  );
}

export default function RecCard({ item, rank }) {
  const [expanded, setExpanded] = useState(false);
  const isUS = item.market === "us_stock";
  const currencySymbol = isUS ? "$ " : "HK$ ";
  const themes = Array.isArray(item.themes) ? item.themes : [];
  const showTrading = item.show_trading_params !== false && item.entry_price;
  const score = item.confidence || item.combined_score || 0;
  const rrRisk = item.entry_price && item.stop_loss ? item.entry_price - item.stop_loss : 0;
  const rrReward = item.take_profit && item.entry_price ? item.take_profit - item.entry_price : 0;
  const rrRatio = rrRisk > 0 ? (rrReward / rrRisk).toFixed(1) : "--";

  return (
    <div className={`rounded-lg border transition-colors ${
      expanded ? "border-[#363a45] bg-[#1e222d]" : "border-[#2a2e39] bg-[#1e222d] hover:border-[#363a45]"
    }`}>
      {/* Header */}
      <div className="cursor-pointer px-5 py-4" onClick={() => setExpanded(!expanded)}>
        {/* Row 1: ticker, name, tags, button */}
        <div className="flex items-center gap-3">
          <span className="rounded bg-[#089981]/15 px-2 py-0.5 text-xs font-bold text-[#089981] font-mono">
            {item.ticker}
          </span>
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
              查看详情
            </Link>
            <button className="text-[#787b86] hover:text-[#d1d4dc] transition-colors"
              onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}>
              {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
          </div>
        </div>

        {/* Row 2: price, change, action, confidence, rr */}
        <div className="mt-2 flex flex-wrap items-center gap-4">
          <span className="text-2xl font-bold tabular-nums text-[#d1d4dc]">
            {currencySymbol}{fmt(item.price)}
          </span>
          <span className={`text-sm font-bold tabular-nums ${
            (item.change_pct || 0) >= 0 ? "text-[#089981]" : "text-[#f23645]"
          }`}>
            {(item.change_pct || 0) >= 0 ? "+" : ""}{fmt(item.change_pct, 2)}%
          </span>
          <ActionArrow action={item.action || item.direction} />
          <ConfidenceBar value={score} />
          {showTrading && (
            <span className="text-xs text-[#787b86]">
              风险回报 1:{rrRatio}
            </span>
          )}
        </div>
      </div>

      {/* Expanded Detail */}
      {expanded && (
        <div className="border-t border-[#2a2e39] px-5 pb-5">
          {showTrading && <TradingPlanGrid item={item} currencySymbol={currencySymbol} />}
          {!showTrading && (
            <div className="mt-4 rounded-lg border border-[#363a45] bg-[#131722] p-4 text-xs text-[#787b86]">
              综合评分较低，暂不展示交易参数
            </div>
          )}
          <AnalysisSection newsReason={item.news_reason} techReason={item.tech_reason} />
          <RiskSection riskFlags={item.risk_flags} riskNote={item.risk_note} />

          {/* Position suggestion */}
          <div className="mt-3 rounded-lg border border-[#fb8c00]/15 bg-[#fb8c00]/5 p-4">
            <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-[#fb8c00]">
              <Crosshair size={14} />
              仓位建议
            </div>
            <p className="text-xs text-[#fb8c00]/70">
              {score >= 70
                ? "评分较高，可适当加大仓位，建议五成仓以上参与。"
                : score >= 50
                  ? "评分中等，建议三成仓试探性参与，设好止损。"
                  : "评分偏低，建议轻仓或观望，等待更好时机。"}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
