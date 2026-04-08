import { useState, useEffect, useMemo, useCallback } from "react";
import { Trophy, TrendingUp, TrendingDown, Clock, RefreshCw, Target, ShieldAlert } from "lucide-react";

const API = "/api";

function useApi() {
  const token = localStorage.getItem("token");
  return (path) =>
    fetch(API + path, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.json());
}

function WinRateRing({ rate, size = 120 }) {
  const r = (size - 12) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - rate / 100);
  const color = rate >= 60 ? "#34d399" : rate >= 45 ? "#f59e0b" : "#fb7185";
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#1e293b" strokeWidth={10} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={10}
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          className="transition-all duration-700" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold" style={{ color }}>{rate.toFixed(1)}%</span>
        <span className="text-[10px] text-neutral-400">{"\u80DC\u7387"}</span>
      </div>
    </div>
  );
}

function StatBox({ icon: Icon, label, value, sub, color = "#e2e8f0" }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4 text-center">
      <div className="mb-2 flex items-center justify-center">
        <Icon size={16} className="text-neutral-400" />
      </div>
      <p className="text-2xl font-bold" style={{ color }}>{value}</p>
      <p className="mt-0.5 text-xs text-neutral-400">{label}</p>
      {sub && <p className="mt-1 text-[11px] text-neutral-400">{sub}</p>}
    </div>
  );
}

function MarketCard({ title, data, color }) {
  if (!data) return null;
  const d = data.all || {};
  const d7 = data["7d"] || {};
  const d30 = data["30d"] || {};
  const rate = d.total_evaluated > 0 ? d.win_rate : 0;

  return (
    <div className="rounded-3xl border border-white/[0.06] bg-white/[0.03] p-6 shadow-xl backdrop-blur-md">
      <div className="flex items-center gap-2 mb-4">
        <div className="h-3 w-3 rounded-full" style={{ background: color }} />
        <span className="text-base font-bold text-white">{title}</span>
      </div>

      <div className="flex items-center gap-8 mb-6">
        <WinRateRing rate={rate} />
        <div className="grid grid-cols-2 gap-3 flex-1">
          <StatBox icon={Trophy} label={"\u603B\u8BC4\u4F30"} value={d.total_evaluated || 0} />
          <StatBox icon={TrendingUp} label={"\u5B8C\u5168\u80DC"} value={d.wins || 0} color="#34d399" />
          {(d.partial_wins || 0) > 0 && (
            <StatBox icon={Target} label={"\u90E8\u5206\u6B62\u76C8"} value={d.partial_wins} color="#818cf8" />
          )}
          {(d.trailing_stops || 0) > 0 && (
            <StatBox icon={TrendingUp} label={"\u8FFD\u8E2A\u6B62\u76C8"} value={d.trailing_stops} color="#38bdf8" />
          )}
          <StatBox icon={TrendingDown} label={"\u6B62\u635F"} value={d.losses || 0} color="#fb7185" />
          <StatBox icon={Clock} label={"\u8D85\u65F6"} value={d.timeouts || 0} color="#94a3b8" />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3 text-center">
          <p className="text-[11px] text-neutral-400 mb-1">{"\u5E73\u5747\u6536\u76CA"}</p>
          <p className="text-sm font-bold" style={{ color: (d.avg_return_pct || 0) >= 0 ? "#34d399" : "#fb7185" }}>
            {(d.avg_return_pct || 0) >= 0 ? "+" : ""}{(d.avg_return_pct || 0).toFixed(2)}%
          </p>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3 text-center">
          <p className="text-[11px] text-neutral-400 mb-1">{"\u5E73\u5747\u76C8\u5229"}</p>
          <p className="text-sm font-bold text-[#34d399]">
            +{(d.avg_win_return_pct || 0).toFixed(2)}%
          </p>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3 text-center">
          <p className="text-[11px] text-neutral-400 mb-1">{"\u5E73\u5747\u4E8F\u635F"}</p>
          <p className="text-sm font-bold text-[#fb7185]">
            {(d.avg_loss_return_pct || 0).toFixed(2)}%
          </p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3 text-center">
          <p className="text-[11px] text-neutral-400 mb-1">Profit Factor</p>
          <p className="text-sm font-bold" style={{ color: (d.profit_factor || 0) >= 1.5 ? "#34d399" : (d.profit_factor || 0) >= 1.0 ? "#f59e0b" : "#fb7185" }}>
            {(d.profit_factor || 0).toFixed(2)}
          </p>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3 text-center">
          <p className="text-[11px] text-neutral-400 mb-1">{"\u6700\u4F73\u4EA4\u6613"}</p>
          <p className="text-sm font-bold text-[#34d399]">
            +{(d.best_trade || 0).toFixed(2)}%
          </p>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3 text-center">
          <p className="text-[11px] text-neutral-400 mb-1">{"\u6700\u5DEE\u4EA4\u6613"}</p>
          <p className="text-sm font-bold text-[#fb7185]">
            {(d.worst_trade || 0).toFixed(2)}%
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3">
          <p className="text-[11px] text-neutral-400 mb-1">{"\u8FD17\u5929\u80DC\u7387"}</p>
          <p className="text-lg font-bold text-white">
            {d7.total_evaluated > 0 ? `${d7.win_rate}%` : "--"}
            <span className="ml-1 text-[11px] text-neutral-400">({d7.wins || 0}W / {d7.total_evaluated || 0}T)</span>
          </p>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-3">
          <p className="text-[11px] text-neutral-400 mb-1">{"\u8FD130\u5929\u80DC\u7387"}</p>
          <p className="text-lg font-bold text-white">
            {d30.total_evaluated > 0 ? `${d30.win_rate}%` : "--"}
            <span className="ml-1 text-[11px] text-neutral-400">({d30.wins || 0}W / {d30.total_evaluated || 0}T)</span>
          </p>
        </div>
      </div>

      {(d.pending || 0) > 0 && (
        <p className="mt-3 text-xs text-neutral-400">
          <Clock size={12} className="inline mr-1" />
          {d.pending} {"\u6761\u63A8\u8350\u5F85\u8BC4\u4F30"}
        </p>
      )}
    </div>
  );
}

function DimensionPanel({ title, items }) {
  if (!items || items.length === 0) return null;
  const labelMap = { short_term: "\u77ED\u7EBF", swing: "\u6CE2\u6BB5", buy: "\u505A\u591A", short: "\u505A\u7A7A" };
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold text-neutral-500">{title}</h4>
      <div className="flex flex-wrap gap-3">
        {items.map((it) => {
          const wr = it.win_rate || 0;
          const wrColor = wr >= 60 ? "#34d399" : wr >= 45 ? "#f59e0b" : "#fb7185";
          return (
            <div key={it.key} className="rounded-2xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 min-w-[180px] flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[11px] font-medium text-neutral-300">
                  {labelMap[it.key] || it.key}
                </span>
                <span className="ml-auto text-sm font-bold" style={{ color: wrColor }}>{wr.toFixed(1)}%</span>
              </div>
              <p className="text-[11px] text-neutral-400">
                {it.wins || 0}W / {it.losses || 0}L
                <span className="ml-2" style={{ color: (it.avg_return || 0) >= 0 ? "#34d399" : "#fb7185" }}>
                  avg {(it.avg_return || 0) >= 0 ? "+" : ""}{(it.avg_return || 0).toFixed(1)}%
                </span>
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TrendChart({ data }) {
  if (!data || data.length === 0) return null;
  const maxTotal = Math.max(...data.map(d => d.total), 1);
  return (
    <div className="rounded-3xl border border-white/[0.06] bg-white/[0.03] p-6">
      <h3 className="mb-4 text-sm font-semibold text-neutral-500">{"\u80DC\u7387\u8D8B\u52BF (\u8FD130\u5929)"}</h3>
      <div className="flex items-end gap-1" style={{ height: 120 }}>
        {data.slice().reverse().map((d, i) => {
          const h = Math.max(4, (d.total / maxTotal) * 100);
          const wr = d.total > 0 ? d.wins / d.total : 0;
          const color = wr >= 0.6 ? '#34d399' : wr >= 0.4 ? '#f59e0b' : '#fb7185';
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1" title={`${d.run_date}: ${d.wins}W/${d.total}T`}>
              <div className="w-full rounded-t" style={{ height: `${h}%`, background: color, minHeight: 4 }} />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-neutral-600">
        <span>{data.length > 0 ? data[data.length - 1]?.run_date : ''}</span>
        <span>{data.length > 0 ? data[0]?.run_date : ''}</span>
      </div>
    </div>
  );
}

function FilterButton({ label, active, onClick }) {
  return (
    <button onClick={onClick}
      className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
        active ? "bg-white/[0.08] text-white font-medium" : "text-neutral-500 hover:text-white hover:bg-white/[0.04]"
      }`}>
      {label}
    </button>
  );
}

function SortHeader({ label, field, sortKey, sortDir, onSort, className = "" }) {
  const active = sortKey === field;
  return (
    <th
      className={`cursor-pointer select-none hover:text-slate-200 ${className}`}
      onClick={() => onSort(field)}
    >
      {label}
      {active && <span className="ml-1">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>}
    </th>
  );
}

function DetailsTable({ items }) {
  const [expandedId, setExpandedId] = useState(null);
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('asc');

  function handleSort(field) {
    if (sortKey === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(field); setSortDir('desc'); }
  }

  const sorted = useMemo(() => {
    if (!sortKey) return items;
    return [...items].sort((a, b) => {
      const va = a[sortKey] ?? -Infinity, vb = b[sortKey] ?? -Infinity;
      if (typeof va === 'string' && typeof vb === 'string') {
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });
  }, [items, sortKey, sortDir]);

  if (!items || items.length === 0) {
    return <p className="text-sm text-slate-400 text-center py-8">{"\u6682\u65E0\u8BC4\u4F30\u8BB0\u5F55"}</p>;
  }
  return (
    <>
      {/* Desktop table */}
      <div className="hidden lg:block">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-800/80 text-slate-400">
                <SortHeader label={"\u65E5\u671F"} field="run_date" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="py-2 text-left font-medium" />
                <th className="py-2 text-left font-medium">{"\u80A1\u7968"}</th>
                <th className="py-2 text-left font-medium">{"\u5E02\u573A"}</th>
                <th className="py-2 text-center font-medium">{"\u65B9\u5411"}</th>
                <th className="py-2 text-center font-medium">{"\u7B56\u7565"}</th>
                <th className="py-2 text-right font-medium">{"\u5165\u573A\u4EF7"}</th>
                <th className="py-2 text-right font-medium">TP1</th>
                <th className="py-2 text-right font-medium">{"\u6B62\u635F"}</th>
                <th className="py-2 text-right font-medium">{"\u51FA\u573A\u4EF7"}</th>
                <SortHeader label={"\u6536\u76CA"} field="return_pct" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="py-2 text-right font-medium" />
                <th className="py-2 text-center font-medium">{"\u6280\u672F"}</th>
                <th className="py-2 text-center font-medium">{"\u65B0\u95FB"}</th>
                <th className="py-2 text-center font-medium">{"\u57FA\u672C"}</th>
                <th className="py-2 text-center font-medium">{"\u7F6E\u4FE1"}</th>
                <SortHeader label={"\u7ED3\u679C"} field="outcome" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="py-2 text-center font-medium" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((it, i) => {
                const outcomeMap = { win: { text: "\u80DC", color: "#34d399", bg: "#34d399" }, trailing_stop: { text: "\u8FFD\u8E2A\u6B62\u76C8", color: "#38bdf8", bg: "#38bdf8" }, partial_win: { text: "\u90E8\u5206\u6B62\u76C8", color: "#818cf8", bg: "#818cf8" }, loss: { text: "\u8D25", color: "#fb7185", bg: "#fb7185" }, timeout: { text: "\u8D85\u65F6", color: "#94a3b8", bg: "#94a3b8" } };
                const o = outcomeMap[it.outcome] || outcomeMap.timeout;
                const mktLabel = it.market === "us_stock" ? "\u7F8E\u80A1" : "\u6E2F\u80A1";
                const isShort = it.direction === "short";
                return (
                  <tr key={it.id || i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                    <td className="py-2 text-slate-200">{it.run_date}</td>
                    <td className="py-2 font-medium text-slate-200">{it.ticker} <span className="text-slate-400">{it.name}</span></td>
                    <td className="py-2 text-slate-400">{mktLabel}</td>
                    <td className="py-2 text-center">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${isShort ? "bg-[#d946ef]/15 text-[#d946ef]" : "bg-[#34d399]/15 text-[#34d399]"}`}>
                        {isShort ? "SHORT" : "LONG"}
                      </span>
                    </td>
                    <td className="py-2 text-center">
                      {it.strategy && (
                        <span className="rounded bg-slate-800/60 px-1.5 py-0.5 text-[10px] text-slate-300">
                          {it.strategy === "swing" ? "\u6CE2\u6BB5" : it.strategy === "short_term" ? "\u77ED\u7EBF" : it.strategy}
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-right text-slate-200">{it.entry_price?.toFixed(2)}</td>
                    <td className="py-2 text-right text-[#34d399]">{it.take_profit?.toFixed(2)}</td>
                    <td className="py-2 text-right text-[#fb7185]">{it.stop_loss?.toFixed(2)}</td>
                    <td className="py-2 text-right text-slate-200">{it.exit_price?.toFixed(2) || "--"}</td>
                    <td className="py-2 text-right font-medium" style={{ color: (it.return_pct || 0) >= 0 ? "#34d399" : "#fb7185" }}>
                      {it.return_pct != null ? `${it.return_pct >= 0 ? "+" : ""}${it.return_pct.toFixed(2)}%` : "--"}
                    </td>
                    <td className="py-2 text-center">
                      {it.tech_score != null ? (
                        <span className="text-[11px] tabular-nums" style={{ color: it.tech_score >= 60 ? "#34d399" : it.tech_score >= 40 ? "#e2e8f0" : "#fb7185" }}>
                          {Math.round(it.tech_score)}
                        </span>
                      ) : <span className="text-slate-600">--</span>}
                    </td>
                    <td className="py-2 text-center">
                      {it.news_score != null ? (
                        <span className="text-[11px] tabular-nums" style={{ color: it.news_score >= 60 ? "#34d399" : it.news_score >= 40 ? "#e2e8f0" : "#fb7185" }}>
                          {Math.round(it.news_score)}
                        </span>
                      ) : <span className="text-slate-600">--</span>}
                    </td>
                    <td className="py-2 text-center">
                      {it.fundamental_score != null ? (
                        <span className="text-[11px] tabular-nums" style={{ color: it.fundamental_score >= 60 ? "#34d399" : it.fundamental_score >= 40 ? "#e2e8f0" : "#fb7185" }}>
                          {Math.round(it.fundamental_score)}
                        </span>
                      ) : <span className="text-slate-600">--</span>}
                    </td>
                    <td className="py-2 text-center">
                      {(it.confidence || it.combined_score) != null ? (
                        <span className="text-[11px] font-semibold tabular-nums" style={{ color: (it.confidence || it.combined_score) >= 65 ? "#34d399" : (it.confidence || it.combined_score) >= 45 ? "#f59e0b" : "#fb7185" }}>
                          {Math.round(it.confidence || it.combined_score)}
                        </span>
                      ) : <span className="text-slate-600">--</span>}
                    </td>
                    <td className="py-2 text-center">
                      <span className="rounded px-2 py-0.5 text-[11px] font-semibold"
                        style={{ color: o.color, background: o.bg + "18" }}>{o.text}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile card list */}
      <div className="lg:hidden space-y-2">
        {sorted.map((it, i) => {
          const outcomeMap = { win: { text: "\u80DC", color: "#34d399", bg: "#34d399" }, trailing_stop: { text: "\u8FFD\u8E2A\u6B62\u76C8", color: "#38bdf8", bg: "#38bdf8" }, partial_win: { text: "\u90E8\u5206\u6B62\u76C8", color: "#818cf8", bg: "#818cf8" }, loss: { text: "\u8D25", color: "#fb7185", bg: "#fb7185" }, timeout: { text: "\u8D85\u65F6", color: "#94a3b8", bg: "#94a3b8" } };
          const o = outcomeMap[it.outcome] || outcomeMap.timeout;
          const isShort = it.direction === "short";
          const cardKey = it.id || i;
          const isExpanded = expandedId === cardKey;
          const scoreColor = (v) => v >= 60 ? "#34d399" : v >= 40 ? "#e2e8f0" : "#fb7185";
          const confValue = it.confidence || it.combined_score;
          const confColor = confValue >= 65 ? "#34d399" : confValue >= 45 ? "#f59e0b" : "#fb7185";

          return (
            <div
              key={cardKey}
              className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-3 cursor-pointer active:bg-slate-800/40 transition-colors"
              onClick={() => setExpandedId(isExpanded ? null : cardKey)}
            >
              {/* Top row: date + outcome */}
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] text-slate-400">{it.run_date}</span>
                <span className="rounded px-2 py-0.5 text-[11px] font-semibold"
                  style={{ color: o.color, background: o.bg + "18" }}>{o.text}</span>
              </div>

              {/* Main: ticker + name + direction */}
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm font-semibold text-slate-200">{it.ticker}</span>
                <span className="text-xs text-slate-400 truncate">{it.name}</span>
                <span className={`ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${isShort ? "bg-[#d946ef]/15 text-[#d946ef]" : "bg-[#34d399]/15 text-[#34d399]"}`}>
                  {isShort ? "SHORT" : "LONG"}
                </span>
              </div>

              {/* Price row */}
              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-slate-400">{it.entry_price?.toFixed(2)}</span>
                <span className="text-slate-600">{"\u2192"}</span>
                <span className="text-slate-200">{it.exit_price?.toFixed(2) || "--"}</span>
                <span className="ml-auto font-medium" style={{ color: (it.return_pct || 0) >= 0 ? "#34d399" : "#fb7185" }}>
                  {it.return_pct != null ? `${it.return_pct >= 0 ? "+" : ""}${it.return_pct.toFixed(2)}%` : "--"}
                </span>
              </div>

              {/* Expanded details */}
              {isExpanded && (
                <div className="mt-3 border-t border-slate-800/50 pt-3 space-y-2">
                  {/* Strategy + SL/TP */}
                  <div className="flex items-center gap-3 text-xs">
                    {it.strategy && (
                      <span className="rounded bg-slate-800/60 px-1.5 py-0.5 text-[10px] text-slate-300">
                        {it.strategy === "swing" ? "\u6CE2\u6BB5" : it.strategy === "short_term" ? "\u77ED\u7EBF" : it.strategy}
                      </span>
                    )}
                    <span className="text-slate-400">
                      SL <span className="text-[#fb7185]">{it.stop_loss?.toFixed(2) || "--"}</span>
                    </span>
                    <span className="text-slate-400">
                      TP <span className="text-[#34d399]">{it.take_profit?.toFixed(2) || "--"}</span>
                    </span>
                  </div>

                  {/* Scores grid */}
                  <div className="grid grid-cols-4 gap-2">
                    <div className="rounded-lg bg-slate-900/60 px-2 py-1.5 text-center">
                      <p className="text-[10px] text-slate-500">{"\u6280\u672F"}</p>
                      {it.tech_score != null ? (
                        <p className="text-xs font-semibold tabular-nums" style={{ color: scoreColor(it.tech_score) }}>{Math.round(it.tech_score)}</p>
                      ) : <p className="text-xs text-slate-600">--</p>}
                    </div>
                    <div className="rounded-lg bg-slate-900/60 px-2 py-1.5 text-center">
                      <p className="text-[10px] text-slate-500">{"\u65B0\u95FB"}</p>
                      {it.news_score != null ? (
                        <p className="text-xs font-semibold tabular-nums" style={{ color: scoreColor(it.news_score) }}>{Math.round(it.news_score)}</p>
                      ) : <p className="text-xs text-slate-600">--</p>}
                    </div>
                    <div className="rounded-lg bg-slate-900/60 px-2 py-1.5 text-center">
                      <p className="text-[10px] text-slate-500">{"\u57FA\u672C"}</p>
                      {it.fundamental_score != null ? (
                        <p className="text-xs font-semibold tabular-nums" style={{ color: scoreColor(it.fundamental_score) }}>{Math.round(it.fundamental_score)}</p>
                      ) : <p className="text-xs text-slate-600">--</p>}
                    </div>
                    <div className="rounded-lg bg-slate-900/60 px-2 py-1.5 text-center">
                      <p className="text-[10px] text-slate-500">{"\u7F6E\u4FE1"}</p>
                      {confValue != null ? (
                        <p className="text-xs font-semibold tabular-nums" style={{ color: confColor }}>{Math.round(confValue)}</p>
                      ) : <p className="text-xs text-slate-600">--</p>}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

export default function WinRatePage() {
  const api = useApi();
  const [summary, setSummary] = useState(null);
  const [details, setDetails] = useState([]);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [filter, setFilter] = useState({ strategy: '', direction: '', outcome: '' });

  const fetchDetails = useCallback(async (f) => {
    try {
      const params = new URLSearchParams();
      params.set('limit', '50');
      if (f.strategy) params.set('strategy', f.strategy);
      if (f.direction) params.set('direction', f.direction);
      if (f.outcome) params.set('outcome', f.outcome);
      const d = await api(`/win-rate/details?${params}`);
      setDetails(d);
    } catch (e) { console.error(e); }
  }, [api]);

  const load = async () => {
    setLoading(true);
    try {
      const [s, d, t] = await Promise.all([
        api("/win-rate/summary"),
        api("/win-rate/details?limit=50"),
        api("/win-rate/trend"),
      ]);
      setSummary(s);
      setDetails(d);
      setTrend(Array.isArray(t) ? t : []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!loading) fetchDetails(filter);
  }, [filter]);

  const toggleFilter = (key, value) => {
    setFilter(prev => ({ ...prev, [key]: prev[key] === value ? '' : value }));
  };

  const handleEvaluate = async () => {
    setEvaluating(true);
    try {
      const token = localStorage.getItem("token");
      await fetch(API + "/win-rate/evaluate", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      await load();
    } catch (e) { console.error(e); }
    setEvaluating(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-light text-white">{"\u7CFB\u7EDF\u80DC\u7387\u7EDF\u8BA1"}</h1>
          <p className="text-sm text-neutral-500">{"\u8FBE\u5230TP1\u5373\u4E3A\u80DC\u51FA\uff0c\u89E6\u53CA\u6B62\u635F\u5373\u4E3A\u5931\u8D25\uff0c\u8D85\u8FC7\u6301\u4ED3\u5929\u6570\u4E3A\u8D85\u65F6"}</p>
        </div>
        <button
          onClick={handleEvaluate}
          disabled={evaluating}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-indigo-500/20 transition-colors hover:bg-indigo-600 disabled:opacity-50"
        >
          <RefreshCw size={14} className={evaluating ? "animate-spin" : ""} />
          {evaluating ? "\u8BC4\u4F30\u4E2D..." : "\u7ACB\u5373\u8BC4\u4F30"}
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <MarketCard title={"\u7F8E\u80A1\u80DC\u7387"} data={summary?.us_stock} color="#818cf8" />
        <MarketCard title={"\u6E2F\u80A1\u80DC\u7387"} data={summary?.hk_stock} color="#f59e0b" />
      </div>

      {/* Dimension breakdowns */}
      {summary && (summary.us_stock?.by_strategy || summary.hk_stock?.by_strategy) && (
        <div className="rounded-3xl border border-white/[0.06] bg-white/[0.03] p-6 space-y-5">
          <h3 className="text-sm font-semibold text-white">{"\u7EF4\u5EA6\u5206\u6790"}</h3>
          <DimensionPanel
            title={"\u6309\u7B56\u7565"}
            items={[
              ...(summary.us_stock?.by_strategy || []),
              ...(summary.hk_stock?.by_strategy || []),
            ].reduce((acc, it) => {
              const existing = acc.find(a => a.key === it.key);
              if (existing) {
                existing.wins += it.wins || 0;
                existing.losses += it.losses || 0;
                existing.total += it.total || 0;
                existing.win_rate = existing.total > 0 ? (existing.wins / existing.total) * 100 : 0;
                existing.avg_return = existing.total > 0
                  ? ((existing.avg_return * (existing.total - (it.total || 0))) + ((it.avg_return || 0) * (it.total || 0))) / existing.total
                  : 0;
              } else {
                acc.push({ ...it });
              }
              return acc;
            }, [])}
          />
          <DimensionPanel
            title={"\u6309\u65B9\u5411"}
            items={[
              ...(summary.us_stock?.by_direction || []),
              ...(summary.hk_stock?.by_direction || []),
            ].reduce((acc, it) => {
              const existing = acc.find(a => a.key === it.key);
              if (existing) {
                existing.wins += it.wins || 0;
                existing.losses += it.losses || 0;
                existing.total += it.total || 0;
                existing.win_rate = existing.total > 0 ? (existing.wins / existing.total) * 100 : 0;
                existing.avg_return = existing.total > 0
                  ? ((existing.avg_return * (existing.total - (it.total || 0))) + ((it.avg_return || 0) * (it.total || 0))) / existing.total
                  : 0;
              } else {
                acc.push({ ...it });
              }
              return acc;
            }, [])}
          />
        </div>
      )}

      {/* Trend chart */}
      <TrendChart data={trend} />

      {/* Details table with filters */}
      <div className="rounded-3xl border border-white/[0.06] bg-white/[0.03] p-5 shadow-xl backdrop-blur-md">
        <h2 className="mb-4 text-sm font-semibold text-white">{"\u8BC4\u4F30\u8BB0\u5F55\u660E\u7EC6"}</h2>

        <div className="flex flex-wrap items-center gap-3 mb-4">
          <FilterButton label={"\u5168\u90E8"} active={!filter.strategy && !filter.direction && !filter.outcome} onClick={() => setFilter({ strategy: '', direction: '', outcome: '' })} />
          <FilterButton label={"\u77ED\u7EBF"} active={filter.strategy === 'short_term'} onClick={() => toggleFilter('strategy', 'short_term')} />
          <FilterButton label={"\u6CE2\u6BB5"} active={filter.strategy === 'swing'} onClick={() => toggleFilter('strategy', 'swing')} />
          <span className="w-px h-4 bg-white/[0.06]" />
          <FilterButton label={"\u505A\u591A"} active={filter.direction === 'buy'} onClick={() => toggleFilter('direction', 'buy')} />
          <FilterButton label={"\u505A\u7A7A"} active={filter.direction === 'short'} onClick={() => toggleFilter('direction', 'short')} />
          <span className="w-px h-4 bg-white/[0.06]" />
          <FilterButton label={"\u80DC"} active={filter.outcome === 'win'} onClick={() => toggleFilter('outcome', 'win')} />
          <FilterButton label={"\u8FFD\u8E2A\u6B62\u76C8"} active={filter.outcome === 'trailing_stop'} onClick={() => toggleFilter('outcome', 'trailing_stop')} />
          <FilterButton label={"\u8D1F"} active={filter.outcome === 'loss'} onClick={() => toggleFilter('outcome', 'loss')} />
          <FilterButton label={"\u8D85\u65F6"} active={filter.outcome === 'timeout'} onClick={() => toggleFilter('outcome', 'timeout')} />
        </div>

        <DetailsTable items={details} />
      </div>
    </div>
  );
}
