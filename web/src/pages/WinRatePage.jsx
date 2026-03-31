import { useState, useEffect } from "react";
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
        <span className="text-[10px] text-slate-400">{"\u80DC\u7387"}</span>
      </div>
    </div>
  );
}

function StatBox({ icon: Icon, label, value, sub, color = "#e2e8f0" }) {
  return (
    <div className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-4 text-center">
      <div className="mb-2 flex items-center justify-center">
        <Icon size={16} className="text-slate-400" />
      </div>
      <p className="text-xl font-bold" style={{ color }}>{value}</p>
      <p className="mt-0.5 text-xs text-slate-400">{label}</p>
      {sub && <p className="mt-1 text-[11px] text-slate-400">{sub}</p>}
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
    <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-6 shadow-xl backdrop-blur-md">
      <div className="flex items-center gap-2 mb-4">
        <div className="h-3 w-3 rounded-full" style={{ background: color }} />
        <span className="text-base font-bold text-slate-200">{title}</span>
      </div>

      <div className="flex items-center gap-8 mb-6">
        <WinRateRing rate={rate} />
        <div className="grid grid-cols-2 gap-3 flex-1">
          <StatBox icon={Trophy} label={"\u603B\u8BC4\u4F30"} value={d.total_evaluated || 0} />
          <StatBox icon={TrendingUp} label={"\u80DC\u51FA"} value={d.wins || 0} color="#34d399" />
          <StatBox icon={TrendingDown} label={"\u6B62\u635F"} value={d.losses || 0} color="#fb7185" />
          <StatBox icon={Clock} label={"\u8D85\u65F6"} value={d.timeouts || 0} color="#94a3b8" />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-3 text-center">
          <p className="text-[11px] text-slate-400 mb-1">{"\u5E73\u5747\u6536\u76CA"}</p>
          <p className="text-sm font-bold" style={{ color: (d.avg_return_pct || 0) >= 0 ? "#34d399" : "#fb7185" }}>
            {(d.avg_return_pct || 0) >= 0 ? "+" : ""}{(d.avg_return_pct || 0).toFixed(2)}%
          </p>
        </div>
        <div className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-3 text-center">
          <p className="text-[11px] text-slate-400 mb-1">{"\u5E73\u5747\u76C8\u5229"}</p>
          <p className="text-sm font-bold text-[#34d399]">
            +{(d.avg_win_return_pct || 0).toFixed(2)}%
          </p>
        </div>
        <div className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-3 text-center">
          <p className="text-[11px] text-slate-400 mb-1">{"\u5E73\u5747\u4E8F\u635F"}</p>
          <p className="text-sm font-bold text-[#fb7185]">
            {(d.avg_loss_return_pct || 0).toFixed(2)}%
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-3">
          <p className="text-[11px] text-slate-400 mb-1">{"\u8FD17\u5929\u80DC\u7387"}</p>
          <p className="text-lg font-bold text-slate-200">
            {d7.total_evaluated > 0 ? `${d7.win_rate}%` : "--"}
            <span className="ml-1 text-[11px] text-slate-400">({d7.wins || 0}W / {d7.total_evaluated || 0}T)</span>
          </p>
        </div>
        <div className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-3">
          <p className="text-[11px] text-slate-400 mb-1">{"\u8FD130\u5929\u80DC\u7387"}</p>
          <p className="text-lg font-bold text-slate-200">
            {d30.total_evaluated > 0 ? `${d30.win_rate}%` : "--"}
            <span className="ml-1 text-[11px] text-slate-400">({d30.wins || 0}W / {d30.total_evaluated || 0}T)</span>
          </p>
        </div>
      </div>

      {(d.pending || 0) > 0 && (
        <p className="mt-3 text-xs text-slate-400">
          <Clock size={12} className="inline mr-1" />
          {d.pending} {"\u6761\u63A8\u8350\u5F85\u8BC4\u4F30"}
        </p>
      )}
    </div>
  );
}

function DetailsTable({ items }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-slate-400 text-center py-8">{"\u6682\u65E0\u8BC4\u4F30\u8BB0\u5F55"}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-800/80 text-slate-400">
            <th className="py-2 text-left font-medium">{"\u65E5\u671F"}</th>
            <th className="py-2 text-left font-medium">{"\u80A1\u7968"}</th>
            <th className="py-2 text-left font-medium">{"\u5E02\u573A"}</th>
            <th className="py-2 text-center font-medium">{"\u65B9\u5411"}</th>
            <th className="py-2 text-right font-medium">{"\u5165\u573A\u4EF7"}</th>
            <th className="py-2 text-right font-medium">TP1</th>
            <th className="py-2 text-right font-medium">{"\u6B62\u635F"}</th>
            <th className="py-2 text-right font-medium">{"\u51FA\u573A\u4EF7"}</th>
            <th className="py-2 text-right font-medium">{"\u6536\u76CA"}</th>
            <th className="py-2 text-center font-medium">{"\u7ED3\u679C"}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, i) => {
            const outcomeMap = { win: { text: "\u80DC", color: "#34d399", bg: "#34d399" }, partial_win: { text: "\u90E8\u5206\u6B62\u76C8", color: "#818cf8", bg: "#818cf8" }, loss: { text: "\u8D25", color: "#fb7185", bg: "#fb7185" }, timeout: { text: "\u8D85\u65F6", color: "#94a3b8", bg: "#94a3b8" } };
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
                <td className="py-2 text-right text-slate-200">{it.entry_price?.toFixed(2)}</td>
                <td className="py-2 text-right text-[#34d399]">{it.take_profit?.toFixed(2)}</td>
                <td className="py-2 text-right text-[#fb7185]">{it.stop_loss?.toFixed(2)}</td>
                <td className="py-2 text-right text-slate-200">{it.exit_price?.toFixed(2) || "--"}</td>
                <td className="py-2 text-right font-medium" style={{ color: (it.return_pct || 0) >= 0 ? "#34d399" : "#fb7185" }}>
                  {it.return_pct != null ? `${it.return_pct >= 0 ? "+" : ""}${it.return_pct.toFixed(2)}%` : "--"}
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
  );
}

export default function WinRatePage() {
  const api = useApi();
  const [summary, setSummary] = useState(null);
  const [details, setDetails] = useState([]);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, d] = await Promise.all([api("/win-rate/summary"), api("/win-rate/details?limit=50")]);
      setSummary(s);
      setDetails(d);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

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
          <h1 className="text-xl font-medium text-white">{"\u7CFB\u7EDF\u80DC\u7387\u7EDF\u8BA1"}</h1>
          <p className="text-xs text-slate-400">{"\u8FBE\u5230TP1\u5373\u4E3A\u80DC\u51FA\uff0c\u89E6\u53CA\u6B62\u635F\u5373\u4E3A\u5931\u8D25\uff0c\u8D85\u8FC7\u6301\u4ED3\u5929\u6570\u4E3A\u8D85\u65F6"}</p>
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

      <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5 shadow-xl backdrop-blur-md">
        <h2 className="mb-4 text-sm font-semibold text-slate-200">{"\u8BC4\u4F30\u8BB0\u5F55\u660E\u7EC6"}</h2>
        <DetailsTable items={details} />
      </div>
    </div>
  );
}
