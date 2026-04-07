import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import Spinner, { PageLoader } from "../components/Spinner";
import PriceChange from "../components/PriceChange";
import { MarketBadge } from "../components/Badge";
import { useToast } from "../components/Toast";
import { Search, Eye, History } from "lucide-react";

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

export default function ScreeningPage() {
  const toast = useToast();
  const [market, setMarket] = useState("us_stock");
  const [topN, setTopN] = useState(20);
  const [results, setResults] = useState([]);
  const [running, setRunning] = useState(false);
  const [latest, setLatest] = useState(null);
  const [historyList, setHistoryList] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('asc');

  function handleSort(field) {
    if (sortKey === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(field); setSortDir('desc'); }
  }

  const sorted = useMemo(() => {
    if (!sortKey) return results;
    return [...results].sort((a, b) => {
      const va = a[sortKey] ?? -Infinity, vb = b[sortKey] ?? -Infinity;
      return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });
  }, [results, sortKey, sortDir]);

  useEffect(() => {
    Promise.allSettled([
      api.latestScreen(market),
      api.screenHistory(10),
    ]).then(([lRes, hRes]) => {
      if (lRes.status === "fulfilled" && lRes.value?.results) {
        setLatest(lRes.value);
        setResults(lRes.value.results);
      }
      if (hRes.status === "fulfilled") setHistoryList(hRes.value || []);
      setLoaded(true);
    });
  }, [market]);

  async function runScreen() {
    setRunning(true);
    try {
      const data = await api.runScreen({ market, top_n: topN });
      setResults(data.results || []);
      setLatest(data);
    } catch (err) {
      toast({ type: "error", message: err.message });
    } finally {
      setRunning(false);
    }
  }

  if (!loaded) return <PageLoader />;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-medium text-white">选股筛选</h1>

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="mb-1 block text-xs text-slate-400">市场</label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value)}
              className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500"
            >
              <option value="us_stock">美股</option>
              <option value="hk_stock">港股</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">数量</label>
            <input
              type="number"
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
              min={5}
              max={100}
              className="w-20 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500"
            />
          </div>
          <button
            onClick={runScreen}
            disabled={running}
            className="flex items-center gap-2 rounded-lg bg-indigo-500 px-5 py-2 text-sm font-medium text-white shadow-lg shadow-indigo-500/20 hover:bg-indigo-600 disabled:opacity-50"
          >
            {running ? <Spinner size="sm" /> : <Search size={16} />}
            {running ? "筛选中..." : "开始筛选"}
          </button>
        </div>
      </Card>

      {results.length > 0 && (
        <section>
          <CardTitle>
            筛选结果 ({results.length}){" "}
            {latest?.ref_date && (
              <span className="font-normal text-slate-500">
                {" "}- {latest.ref_date}
              </span>
            )}
          </CardTitle>
          {/* Desktop table */}
          <div className="hidden lg:block">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-800/40 text-xs text-slate-500">
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">代码</th>
                    <th className="px-3 py-2">名称</th>
                    <th className="px-3 py-2">市场</th>
                    <SortHeader label="价格" field="price" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="px-3 py-2 text-right" />
                    <SortHeader label="涨跌" field="change_pct" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="px-3 py-2 text-right" />
                    <SortHeader label="成交量" field="volume" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="px-3 py-2 text-right" />
                    <SortHeader label="市值" field="market_cap" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="px-3 py-2 text-right" />
                    <SortHeader label="PE(TTM)" field="pe_ttm" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="px-3 py-2 text-right" />
                    <SortHeader label="PB" field="pb" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="px-3 py-2 text-right" />
                    <SortHeader label="评分" field="score" sortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="px-3 py-2 text-right" />
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((r, i) => (
                    <tr
                      key={r.ticker}
                      className="border-b border-slate-800/40 hover:bg-slate-800/30"
                    >
                      <td className="px-3 py-2 text-slate-500">{i + 1}</td>
                      <td className="px-3 py-2 font-mono font-semibold">{r.ticker}</td>
                      <td className="max-w-[200px] truncate px-3 py-2 text-slate-400">{r.name}</td>
                      <td className="px-3 py-2"><MarketBadge market={r.market} /></td>
                      <td className="px-3 py-2 text-right font-mono">{r.price?.toFixed(2) ?? "--"}</td>
                      <td className="px-3 py-2 text-right"><PriceChange value={r.change_pct} /></td>
                      <td className="px-3 py-2 text-right text-xs text-slate-500">
                        {r.volume ? (r.volume >= 1e9 ? (r.volume / 1e9).toFixed(1) + "B" : (r.volume / 1e6).toFixed(1) + "M") : "--"}
                      </td>
                      <td className="px-3 py-2 text-right text-xs text-slate-500">
                        {r.market_cap ? (r.market_cap >= 1e12 ? (r.market_cap / 1e12).toFixed(1) + "T" : r.market_cap >= 1e9 ? (r.market_cap / 1e9).toFixed(1) + "B" : (r.market_cap / 1e6).toFixed(0) + "M") : "--"}
                      </td>
                      <td className="px-3 py-2 text-right text-xs text-slate-400">
                        {r.pe_ttm != null && r.pe_ttm > 0 ? r.pe_ttm.toFixed(1) : "--"}
                      </td>
                      <td className="px-3 py-2 text-right text-xs text-slate-400">
                        {r.pb != null && r.pb > 0 ? r.pb.toFixed(2) : "--"}
                      </td>
                      <td className="px-3 py-2 text-right font-semibold text-indigo-400">{r.score?.toFixed(1)}</td>
                      <td className="px-3 py-2">
                        <Link
                          to={`/analysis?ticker=${r.ticker}&market=${r.market}`}
                          className="text-slate-500 hover:text-indigo-400"
                        >
                          <Eye size={14} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Mobile card list */}
          <div className="lg:hidden space-y-2">
            {sorted.map((r, i) => (
              <div
                key={r.ticker}
                className="rounded-xl border border-slate-800/60 bg-slate-950/50 p-3"
              >
                {/* Top row: rank + ticker + market badge + score */}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">#{i + 1}</span>
                  <span className="font-mono font-bold text-sm">{r.ticker}</span>
                  <MarketBadge market={r.market} />
                  <span className="ml-auto font-semibold text-indigo-400">{r.score?.toFixed(1)}</span>
                </div>

                {/* Name */}
                <p className="mt-1 truncate text-xs text-slate-400">{r.name}</p>

                {/* Metrics 2x2 grid */}
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">价格</span>
                    <span className="font-mono">{r.price?.toFixed(2) ?? "--"} <PriceChange value={r.change_pct} /></span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">PE(TTM)</span>
                    <span className="text-slate-400">{r.pe_ttm != null && r.pe_ttm > 0 ? r.pe_ttm.toFixed(1) : "--"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">PB</span>
                    <span className="text-slate-400">{r.pb != null && r.pb > 0 ? r.pb.toFixed(2) : "--"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">成交量</span>
                    <span className="text-slate-500">{r.volume ? (r.volume >= 1e9 ? (r.volume / 1e9).toFixed(1) + "B" : (r.volume / 1e6).toFixed(1) + "M") : "--"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">市值</span>
                    <span className="text-slate-500">{r.market_cap ? (r.market_cap >= 1e12 ? (r.market_cap / 1e12).toFixed(1) + "T" : r.market_cap >= 1e9 ? (r.market_cap / 1e9).toFixed(1) + "B" : (r.market_cap / 1e6).toFixed(0) + "M") : "--"}</span>
                  </div>
                </div>

                {/* Analysis link */}
                <div className="mt-2 flex justify-end">
                  <Link
                    to={`/analysis?ticker=${r.ticker}&market=${r.market}`}
                    className="text-slate-500 hover:text-indigo-400"
                  >
                    <Eye size={14} />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {historyList.length > 0 && (
        <section>
          <CardTitle>
            <History size={14} className="mr-1 inline" /> 最近筛选
          </CardTitle>
          <div className="space-y-1">
            {historyList.map((h, i) => (
              <Card key={i} className="flex items-center justify-between !py-2 rounded-xl border border-slate-800/60 bg-slate-950/50">
                <span className="text-xs text-slate-400">
                  {h.ref_date} - {h.market}
                </span>
                <span className="text-xs text-slate-500">
                  {h.result_count} 条结果
                </span>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
