import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import Spinner, { PageLoader } from "../components/Spinner";
import PriceChange from "../components/PriceChange";
import { MarketBadge } from "../components/Badge";
import { Search, Eye, History } from "lucide-react";

export default function ScreeningPage() {
  const [market, setMarket] = useState("us_stock");
  const [topN, setTopN] = useState(20);
  const [results, setResults] = useState([]);
  const [running, setRunning] = useState(false);
  const [latest, setLatest] = useState(null);
  const [historyList, setHistoryList] = useState([]);
  const [loaded, setLoaded] = useState(false);

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
      alert(err.message);
    } finally {
      setRunning(false);
    }
  }

  if (!loaded) return <PageLoader />;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-medium text-white">閫夎偂绛涢€�</h1>

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="mb-1 block text-xs text-slate-400">甯傚満</label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value)}
              className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500"
            >
              <option value="us_stock">缇庤偂</option>
              <option value="hk_stock">娓偂</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">鏁伴噺</label>
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
            {running ? "绛涢€変腑..." : "寮€濮嬬瓫閫�"}
          </button>
        </div>
      </Card>

      {results.length > 0 && (
        <section>
          <CardTitle>
            绛涢€夌粨鏋� ({results.length}){" "}
            {latest?.ref_date && (
              <span className="font-normal text-slate-500">
                {" "}- {latest.ref_date}
              </span>
            )}
          </CardTitle>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-800/40 text-xs text-slate-500">
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">浠ｇ爜</th>
                  <th className="px-3 py-2">鍚嶇О</th>
                  <th className="px-3 py-2">甯傚満</th>
                  <th className="px-3 py-2 text-right">浠锋牸</th>
                  <th className="px-3 py-2 text-right">娑ㄨ穼</th>
                  <th className="px-3 py-2 text-right">璇勫垎</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
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
        </section>
      )}

      {historyList.length > 0 && (
        <section>
          <CardTitle>
            <History size={14} className="mr-1 inline" /> 鏈€杩戠瓫閫�
          </CardTitle>
          <div className="space-y-1">
            {historyList.map((h, i) => (
              <Card key={i} className="flex items-center justify-between !py-2 rounded-xl border border-slate-800/60 bg-slate-950/50">
                <span className="text-xs text-slate-400">
                  {h.ref_date} - {h.market}
                </span>
                <span className="text-xs text-slate-500">
                  {h.result_count} 鏉＄粨鏋�
                </span>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
