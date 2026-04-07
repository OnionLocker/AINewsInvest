import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import { PageLoader } from "../components/Spinner";
import PriceChange from "../components/PriceChange";
import { MarketBadge } from "../components/Badge";
import { Heart, Trash2, Eye, RefreshCw, Plus } from "lucide-react";

export default function WatchlistPage() {
  const [items, setItems] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addTicker, setAddTicker] = useState("");
  const [addMarket, setAddMarket] = useState("us_stock");
  const [addName, setAddName] = useState("");

  const load = useCallback(async () => {
    try {
      const [wl, qt] = await Promise.all([
        api.getWatchlist(),
        api.watchlistQuotes(),
      ]);
      setItems(wl || []);
      setQuotes(qt || []);
    } catch {
      /* silent */
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function refresh() {
    setRefreshing(true);
    try {
      const qt = await api.watchlistQuotes();
      setQuotes(qt || []);
    } catch {
      /* silent */
    }
    setRefreshing(false);
  }

  async function handleRemove(id) {
    try {
      await api.removeWatchlist(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
      setQuotes((prev) => prev.filter((x) => x.watchlist_id !== id));
    } catch (err) {
      alert(err.message);
    }
  }

  async function handleAdd(e) {
    e.preventDefault();
    if (!addTicker) return;
    try {
      await api.addWatchlist({
        ticker: addTicker.toUpperCase(),
        name: addName || addTicker.toUpperCase(),
        market: addMarket,
      });
      setAddTicker("");
      setAddName("");
      setShowAdd(false);
      load();
    } catch (err) {
      alert(err.message);
    }
  }

  if (loading) return <PageLoader />;

  const quoteMap = {};
  quotes.forEach((q) => {
    quoteMap[q.watchlist_id] = q;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-medium text-white">
          <Heart size={20} className="mr-2 inline text-rose-400" />
          自��股
        </h1>
        <div className="flex gap-2">
          <button
            onClick={refresh}
            disabled={refreshing}
            className="flex items-center gap-1 rounded-lg border border-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800/50"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            刷新
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="flex items-center gap-1 rounded-lg bg-indigo-500 px-3 py-1.5 text-xs text-white shadow-lg shadow-indigo-500/20 hover:bg-indigo-600"
          >
            <Plus size={14} /> 添加
          </button>
        </div>
      </div>

      {showAdd && (
        <Card>
          <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-xs text-slate-400">代码</label>
              <input
                value={addTicker}
                onChange={(e) => setAddTicker(e.target.value.toUpperCase())}
                placeholder="AAPL"
                className="w-28 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm uppercase text-slate-200 outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">名称</label>
              <input
                value={addName}
                onChange={(e) => setAddName(e.target.value)}
                placeholder="Apple Inc."
                className="w-40 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">市场</label>
              <select
                value={addMarket}
                onChange={(e) => setAddMarket(e.target.value)}
                className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500"
              >
                <option value="us_stock">美股</option>
                <option value="hk_stock">港股</option>
              </select>
            </div>
            <button
              type="submit"
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm text-white shadow-lg shadow-indigo-500/20 hover:bg-indigo-600"
            >
              添加
            </button>
          </form>
        </Card>
      )}

      {items.length === 0 ? (
        <Card className="py-10 text-center text-sm text-slate-500">
          自��股列表为空，请添加股票〄1�7
        </Card>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-800/40 text-xs text-slate-500">
                <th className="px-3 py-2">代码</th>
                <th className="px-3 py-2">名称</th>
                <th className="px-3 py-2">市场</th>
                <th className="px-3 py-2 text-right">价格</th>
                <th className="px-3 py-2 text-right">涨跌</th>
                <th className="px-3 py-2 text-right">成交量</th>
                <th className="px-3 py-2">备注</th>
                <th className="px-3 py-2 text-right">添加时间</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const q = quoteMap[item.id];
                return (
                  <tr
                    key={item.id}
                    className="border-b border-slate-800/40 hover:bg-slate-800/30"
                  >
                    <td className="px-3 py-2 font-mono font-semibold">{item.ticker}</td>
                    <td className="max-w-[180px] truncate px-3 py-2 text-slate-400">{item.name}</td>
                    <td className="px-3 py-2"><MarketBadge market={item.market} /></td>
                    <td className="px-3 py-2 text-right font-mono">{q?.price?.toFixed(2) ?? "--"}</td>
                    <td className="px-3 py-2 text-right"><PriceChange value={q?.change_pct} /></td>
                    <td className="px-3 py-2 text-right text-xs text-slate-500">
                      {q?.volume ? (q.volume / 1e6).toFixed(1) + "M" : "--"}
                    </td>
                    <td className="max-w-[150px] truncate px-3 py-2 text-xs text-slate-500" title={item.note || ""}>
                      {item.note || "--"}
                    </td>
                    <td className="px-3 py-2 text-right text-[10px] text-slate-500 whitespace-nowrap">
                      {item.created_at ? new Date(item.created_at).toLocaleDateString("zh-CN") : "--"}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Link
                          to={"/analysis?ticker=" + item.ticker + "&market=" + item.market}
                          className="text-slate-500 hover:text-indigo-400"
                        >
                          <Eye size={14} />
                        </Link>
                        <button
                          onClick={() => handleRemove(item.id)}
                          className="text-slate-500 hover:text-rose-400"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
