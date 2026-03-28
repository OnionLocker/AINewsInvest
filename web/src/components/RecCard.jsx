import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp, AlertTriangle, Newspaper, BarChart3, Target, Plus } from "lucide-react";
import Badge from "./Badge";
import { MarketBadge, StrategyBadge } from "./Badge";

function fmt(v, decimals = 2) {
  if (v == null || isNaN(v)) return "--";
  return Number(v).toFixed(decimals);
}

function pctFromEntry(tp, entry) {
  if (!tp || !entry || entry === 0) return null;
  return (((tp - entry) / entry) * 100).toFixed(1);
}

function ActionTag({ action }) {
  const map = {
    buy: { label: "买入", cls: "text-green-400" },
    strong_buy: { label: "强烈买入", cls: "text-green-300" },
    hold: { label: "观望", cls: "text-yellow-400" },
    avoid: { label: "回避", cls: "text-red-400" },
  };
  const a = (action || "").toLowerCase();
  const info = map[a] || { label: action || "观望", cls: "text-yellow-400" };
  return <span className={`font-semibold ${info.cls}`}>~&gt; {info.label}</span>;
}

function ConfidenceBar({ value }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const color =
    v >= 70 ? "bg-green-500" : v >= 55 ? "bg-blue-500" : v >= 40 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-400">置信度 {v}%</span>
      <div className="h-2 w-20 overflow-hidden rounded-full bg-surface-3">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function PriceBar({ sl, entry, tp }) {
  if (!sl || !entry || !tp || sl >= tp) return null;
  const range = tp - sl;
  const entryPct = ((entry - sl) / range) * 100;

  return (
    <div className="relative mt-3 flex h-7 w-full overflow-hidden rounded-md text-[10px] font-bold">
      <div
        className="flex items-center justify-center bg-red-600/80 text-red-100"
        style={{ width: `${entryPct}%`, minWidth: "60px" }}
      >
        SL {fmt(sl)}
      </div>
      <div
        className="flex items-center justify-center bg-surface-3 text-gray-200"
        style={{ width: `${100 - entryPct}%`, minWidth: "60px" }}
      >
        入 {fmt(entry)}
      </div>
      <div
        className="flex items-center justify-center bg-green-600/80 text-green-100"
        style={{ minWidth: "60px", flex: 1 }}
      >
        TP {fmt(tp)}
      </div>
    </div>
  );
}

function TradingPlanGrid({ item, currencySymbol }) {
  const entry = item.entry_price;
  const pctTP1 = pctFromEntry(item.take_profit, entry);
  const pctTP2 = pctFromEntry(item.take_profit_2, entry);
  const pctTP3 = pctFromEntry(item.take_profit_3, entry);

  return (
    <div className="mt-4 rounded-xl border border-surface-3 bg-surface-0/50 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Target size={14} className="text-brand-400" />
        <span className="text-sm font-semibold text-gray-200">交易计划</span>
        <Badge variant="gray">建议持仓 {item.holding_days || 3} 天</Badge>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-surface-3 bg-surface-1 p-3 text-center">
          <div className="mb-1 text-[11px] text-gray-400">入场价位</div>
          <div className="text-xl font-bold text-white">{fmt(entry)}</div>
          <div className="mt-1 text-[10px] text-gray-500">限价挂单</div>
        </div>
        <div className="rounded-lg border border-red-500/30 bg-surface-1 p-3 text-center">
          <div className="mb-1 text-[11px] text-red-400">止损价位</div>
          <div className="text-xl font-bold text-red-400">{fmt(item.stop_loss)}</div>
        </div>
        <div className="rounded-lg border border-cyan-500/30 bg-surface-1 p-3 text-center">
          <div className="mb-1 text-[11px] text-cyan-400">加仓价位</div>
          <div className="text-xl font-bold text-cyan-300">{fmt(item.entry_2)}</div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-green-500/20 bg-surface-1 p-3 text-center">
          <div className="mb-1 text-[11px] text-green-400">TP1 保守</div>
          <div className="text-lg font-bold text-green-300">{fmt(item.take_profit)}</div>
          {pctTP1 && <div className="mt-0.5 text-[11px] text-green-500">+{pctTP1}%</div>}
        </div>
        <div className="rounded-lg border border-green-500/20 bg-surface-1 p-3 text-center">
          <div className="mb-1 text-[11px] text-green-400">TP2 标准</div>
          <div className="text-lg font-bold text-green-300">{fmt(item.take_profit_2)}</div>
          {pctTP2 && <div className="mt-0.5 text-[11px] text-green-500">+{pctTP2}%</div>}
        </div>
        <div className="rounded-lg border border-green-500/20 bg-surface-1 p-3 text-center">
          <div className="mb-1 text-[11px] text-green-400">TP3 激进</div>
          <div className="text-lg font-bold text-green-300">{fmt(item.take_profit_3)}</div>
          {pctTP3 && <div className="mt-0.5 text-[11px] text-green-500">+{pctTP3}%</div>}
        </div>
      </div>

      <PriceBar sl={item.stop_loss} entry={entry} tp={item.take_profit} />

      <p className="mt-2 text-[11px] text-gray-500">
        💡 入场价为建议挂限价单价位，等回调至该价位自动成交
      </p>
    </div>
  );
}

function AnalysisSection({ newsReason, techReason }) {
  if (!newsReason && !techReason) return null;
  return (
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      {newsReason && (
        <div className="rounded-lg border border-surface-3 bg-surface-1 p-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-gray-300">
            <Newspaper size={13} className="text-blue-400" />
            新闻面
          </div>
          <p className="text-xs leading-relaxed text-gray-400">{newsReason}</p>
        </div>
      )}
      {techReason && (
        <div className="rounded-lg border border-surface-3 bg-surface-1 p-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-gray-300">
            <BarChart3 size={13} className="text-purple-400" />
            技术面
          </div>
          <p className="text-xs leading-relaxed text-gray-400">{techReason}</p>
        </div>
      )}
    </div>
  );
}

function RiskSection({ riskFlags, riskNote }) {
  if ((!riskFlags || riskFlags.length === 0) && !riskNote) return null;
  return (
    <div className="mt-3 rounded-lg border border-yellow-600/20 bg-yellow-900/10 p-3">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-yellow-400">
        <AlertTriangle size={13} />
        风险提示
      </div>
      {riskNote && <p className="text-xs text-yellow-300/70">{riskNote}</p>}
      {riskFlags && riskFlags.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {riskFlags.map((f, i) => (
            <span
              key={i}
              className="rounded bg-yellow-800/30 px-1.5 py-0.5 text-[10px] text-yellow-400/80"
            >
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function RecCard({ item }) {
  const [expanded, setExpanded] = useState(false);
  const isUS = item.market === "us_stock";
  const currencySymbol = isUS ? "$" : "HK$";
  const themes = item.themes || [];
  const showTrading = item.show_trading_params !== false && item.entry_price;

  const rrRisk = item.entry_price && item.stop_loss ? item.entry_price - item.stop_loss : 0;
  const rrReward = item.take_profit && item.entry_price ? item.take_profit - item.entry_price : 0;
  const rrRatio = rrRisk > 0 ? (rrReward / rrRisk).toFixed(1) : "--";

  return (
    <div className="rounded-xl border border-surface-3 bg-surface-1 p-5 transition-all hover:border-surface-3/80">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-brand-600/30 px-2 py-0.5 text-xs font-bold text-brand-300">
              {item.ticker}
            </span>
            <span className="text-base font-bold text-white">{item.name}</span>
            <StrategyBadge strategy={item.strategy} />
            {themes.map((t, i) => (
              <Badge key={i} variant="gray">
                {t}
              </Badge>
            ))}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-4 text-sm">
            <span className="text-lg font-bold text-white">
              {currencySymbol} {fmt(item.price)}
            </span>
            <span className={item.change_pct >= 0 ? "font-semibold text-green-400" : "font-semibold text-red-400"}>
              {item.change_pct >= 0 ? "+" : ""}
              {fmt(item.change_pct, 2)}%
            </span>
            <ActionTag action={item.action || item.direction} />
            <ConfidenceBar value={item.confidence || item.combined_score} />
            {showTrading && (
              <span className="text-xs text-gray-400">
                风险回报 1:{rrRatio}
              </span>
            )}
          </div>
        </div>

        <button
          onClick={() => setExpanded(!expanded)}
          className="shrink-0 rounded-lg p-2 text-gray-400 transition-colors hover:bg-surface-2 hover:text-white"
        >
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>
      </div>

      {expanded && (
        <div className="mt-1">
          {showTrading && (
            <TradingPlanGrid item={item} currencySymbol={currencySymbol} />
          )}
          {!showTrading && (
            <div className="mt-4 rounded-lg border border-yellow-600/20 bg-yellow-900/10 p-3 text-xs text-yellow-400">
              综合评分较低，暂不展示交易参数
            </div>
          )}
          <AnalysisSection
            newsReason={item.news_reason}
            techReason={item.tech_reason}
          />
          <RiskSection riskFlags={item.risk_flags} riskNote={item.risk_note} />
          <div className="mt-3 text-right">
            <Link
              to={`/analysis?ticker=${item.ticker}&market=${item.market}`}
              className="text-xs text-brand-400 hover:underline"
            >
              查看详细分析 &rarr;
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
