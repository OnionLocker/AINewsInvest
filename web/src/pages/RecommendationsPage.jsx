import { useState, useEffect } from "react";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import { PageLoader } from "../components/Spinner";
import PriceChange from "../components/PriceChange";
import RecCard from "../components/RecCard";
import MarketSentimentPanel from "../components/MarketSentimentPanel";
import { Calendar, TrendingUp } from "lucide-react";

const MARKET_CFG = {
  us: {
    title: "美股推荐",
    mkt: "us_stock",
    indexFilter: (idx) => idx.market === "us_stock",
    bg: "bg-gradient-to-br from-brand-950/80 via-brand-900/40 to-surface-1",
  },
  hk: {
    title: "港股推荐",
    mkt: "hk_stock",
    indexFilter: (idx) => idx.market === "hk_stock",
    bg: "bg-gradient-to-br from-amber-950/80 via-amber-900/40 to-surface-1",
  },
};

function IndexCard({ idx, bg }) {
  return (
    <div className={`rounded-xl ${bg} p-5 shadow-lg ring-1 ring-white/5`}>
      <p className="text-sm font-semibold text-gray-300 tracking-wide">
        {idx.name || idx.symbol}
      </p>
      <p className="mt-2 text-2xl font-bold tabular-nums tracking-tight text-white">
        {idx.price?.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }) ?? "--"}
      </p>
      <div className="mt-1">
        <PriceChange value={idx.change_pct} size="lg" />
      </div>
    </div>
  );
}

export default function RecommendationsPage({ market = "us" }) {
  const cfg = MARKET_CFG[market] || MARKET_CFG.us;

  const [indices, setIndices] = useState([]);
  const [sentiment, setSentiment] = useState(null);
  const [today, setToday] = useState(null);
  const [history, setHistory] = useState([]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setDetail(null);
    setSentiment(null);
    Promise.allSettled([
      api.marketOverview(),
      api.marketTodayRecs(market),
      api.marketRecHistory(market, 30),
      api.marketSentiment(market),
    ]).then(([idxRes, tRes, hRes, sRes]) => {
      if (idxRes.status === "fulfilled") {
        const all = idxRes.value || [];
        setIndices(all.filter(cfg.indexFilter));
      }
      if (tRes.status === "fulfilled") setToday(tRes.value);
      else setToday(null);
      if (hRes.status === "fulfilled") setHistory(hRes.value || []);
      else setHistory([]);
      if (sRes.status === "fulfilled") setSentiment(sRes.value);
      setLoading(false);
    });
  }, [market]);

  async function loadDate(date) {
    try {
      const d = await api.marketRecByDate(market, date);
      setDetail(d);
    } catch {
      setDetail(null);
    }
  }

  if (loading) return <PageLoader />;

  const items = detail?.items || today?.items || [];
  const viewingDate = detail ? detail.run?.ref_date : "今日";

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">{cfg.title}</h1>

      {/* Market indices */}
      <section>
        <div className={`grid gap-4 ${indices.length <= 2 ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}>
          {indices.map((idx, i) => (
            <IndexCard key={i} idx={idx} bg={cfg.bg} />
          ))}
        </div>
      </section>

      {/* Market sentiment panel */}
      {sentiment && <MarketSentimentPanel data={sentiment} market={market} />}

      {/* Display message */}
      {today?.display_message && !detail && (
        <div className="rounded-lg border border-yellow-600/20 bg-yellow-900/10 px-4 py-3 text-sm text-yellow-400">
          {today.display_message}
        </div>
      )}

      {/* Recommendations */}
      <div className="flex gap-6">
        {/* Sidebar: history dates */}
        <div className="hidden w-48 shrink-0 md:block">
          <CardTitle>
            <Calendar size={14} className="mr-1 inline" /> 历史记录
          </CardTitle>
          <div className="space-y-1">
            <button
              onClick={() => setDetail(null)}
              className={`w-full rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                !detail
                  ? "bg-brand-600/20 text-brand-400"
                  : "text-gray-400 hover:bg-surface-2"
              }`}
            >
              今日
            </button>
            {history.map((h) => (
              <button
                key={h.id || h.ref_date}
                onClick={() => loadDate(h.ref_date)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                  detail?.run?.ref_date === h.ref_date
                    ? "bg-brand-600/20 text-brand-400"
                    : "text-gray-400 hover:bg-surface-2"
                }`}
              >
                <span>{h.ref_date}</span>
                <span className="text-gray-600">
                  {h.published_count ?? h.result_count}
                </span>
              </button>
            ))}
            {history.length === 0 && (
              <p className="px-3 text-xs text-gray-600">暂无历史</p>
            )}
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1">
          <div className="mb-4 flex items-center gap-2">
            <CardTitle className="!mb-0">
              <TrendingUp size={14} className="mr-1 inline text-brand-400" />
              推荐列表
            </CardTitle>
            <span className="text-xs text-gray-500">
              {viewingDate}
              {items.length > 0 && ` \u00b7 ${items.length} 只`}
            </span>
          </div>

          {items.length === 0 ? (
            <Card className="py-16 text-center text-sm text-gray-500">
              该日期暂无推荐数据
            </Card>
          ) : (
            <div className="space-y-4">
              {items.map((item, i) => (
                <RecCard key={item.ticker || i} item={item} />
              ))}
            </div>
          )}

          {/* Mobile history selector */}
          <div className="mt-6 md:hidden">
            <CardTitle>历史记录</CardTitle>
            <select
              className="w-full rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm"
              value={detail?.run?.ref_date || ""}
              onChange={(e) =>
                e.target.value ? loadDate(e.target.value) : setDetail(null)
              }
            >
              <option value="">今日</option>
              {history.map((h) => (
                <option key={h.ref_date} value={h.ref_date}>
                  {h.ref_date} ({h.published_count ?? h.result_count})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}
