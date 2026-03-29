import { useState, useEffect } from "react";
import api from "../api";
import PriceChange from "../components/PriceChange";
import RecCard from "../components/RecCard";
import MarketSentimentPanel from "../components/MarketSentimentPanel";
import { Calendar, Clock } from "lucide-react";

const MARKET_CFG = {
  us: {
    title: "美股推荐",
    mkt: "us_stock",
    indexFilter: (idx) => idx.market === "us_stock",
  },
  hk: {
    title: "港股推荐",
    mkt: "hk_stock",
    indexFilter: (idx) => idx.market === "hk_stock",
  },
};

function IndexCard({ idx }) {
  return (
    <div className="rounded-lg border border-[#2a2e39] bg-[#1e222d] p-4">
      <p className="text-xs text-[#787b86]">{idx.name || idx.symbol}</p>
      <p className="mt-1.5 text-xl font-semibold tabular-nums text-[#d1d4dc]">
        {idx.price?.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }) ?? "--"}
      </p>
      <div className="mt-1">
        <PriceChange value={idx.change_pct} />
      </div>
    </div>
  );
}

function Skeleton({ className }) {
  return <div className={`animate-pulse rounded bg-[#2a2e39] ${className}`} />;
}

export default function RecommendationsPage({ market = "us" }) {
  const cfg = MARKET_CFG[market] || MARKET_CFG.us;

  const [indices, setIndices] = useState([]);
  const [sentiment, setSentiment] = useState(null);
  const [sentimentLoading, setSentimentLoading] = useState(true);
  const [today, setToday] = useState(null);
  const [history, setHistory] = useState([]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setDetail(null);
    setSentiment(null);
    setSentimentLoading(true);

    Promise.allSettled([
      api.marketOverview(),
      api.marketTodayRecs(market),
      api.marketRecHistory(market, 30),
    ]).then(([idxRes, tRes, hRes]) => {
      if (idxRes.status === "fulfilled") {
        setIndices((idxRes.value || []).filter(cfg.indexFilter));
      }
      if (tRes.status === "fulfilled") setToday(tRes.value);
      else setToday(null);
      if (hRes.status === "fulfilled") setHistory(hRes.value || []);
      else setHistory([]);
      setLoading(false);
    });

    api
      .marketSentiment(market)
      .then((d) => setSentiment(d))
      .catch(() => {})
      .finally(() => setSentimentLoading(false));
  }, [market]);

  async function loadDate(date) {
    try {
      const d = await api.marketRecByDate(market, date);
      setDetail(d);
    } catch {
      setDetail(null);
    }
  }

  const items = detail?.items || today?.items || [];
  const viewingDate = detail ? detail.run?.ref_date : "今日";

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <h1 className="text-lg font-semibold text-[#d1d4dc]">{cfg.title}</h1>

      {/* Market indices */}
      <section>
        {loading ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {[1,2,3].map(i => (
              <div key={i} className="rounded-lg border border-[#2a2e39] bg-[#1e222d] p-4">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-2 h-6 w-28" />
                <Skeleton className="mt-2 h-3 w-14" />
              </div>
            ))}
          </div>
        ) : (
          <div className={`grid gap-3 ${indices.length <= 2 ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}>
            {indices.map((idx, i) => (
              <IndexCard key={i} idx={idx} />
            ))}
          </div>
        )}
      </section>

      {/* Market sentiment */}
      {sentimentLoading ? (
        <div className="rounded-lg border border-[#2a2e39] bg-[#1e222d] p-5">
          <Skeleton className="mb-4 h-4 w-28" />
          <div className="grid gap-4 md:grid-cols-3">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
        </div>
      ) : (
        sentiment && <MarketSentimentPanel data={sentiment} market={market} />
      )}

      {/* Display message */}
      {today?.display_message && !detail && (
        <div className="flex items-center gap-2 rounded-lg border border-[#363a45] bg-[#1e222d] px-4 py-3 text-xs text-[#787b86]">
          <Clock size={14} />
          {today.display_message}
        </div>
      )}

      {/* History bar + Rec header */}
      <div className="flex items-center gap-3">
        <Calendar size={13} className="text-[#787b86]" />
        <p className="text-xs font-medium text-[#787b86]">历史记录</p>
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-thin">
          <button
            onClick={() => setDetail(null)}
            className={`shrink-0 rounded px-2.5 py-1 text-xs transition-colors ${
              !detail
                ? "bg-brand-500/10 text-brand-500 font-semibold"
                : "text-[#787b86] hover:text-[#d1d4dc]"
            }`}
          >
            今日推荐
          </button>
          {history.map((h) => (
            <button
              key={h.id || h.ref_date}
              onClick={() => loadDate(h.ref_date)}
              className={`shrink-0 rounded px-2.5 py-1 text-xs transition-colors ${
                detail?.run?.ref_date === h.ref_date
                  ? "bg-brand-500/10 text-brand-500 font-semibold"
                  : "text-[#787b86] hover:text-[#d1d4dc]"
              }`}
            >
              {h.ref_date}
              <span className="ml-1 text-[#363a45]">{h.published_count ?? h.result_count}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Recommendations - full width */}
      <div>
        <div className="mb-3 flex items-center gap-2">
          <p className="text-sm font-semibold text-[#d1d4dc]">推荐列表</p>
          <span className="text-xs text-[#787b86]">
            {viewingDate} · {items.length} 只
          </span>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1,2,3].map(i => (
              <div key={i} className="rounded-lg border border-[#2a2e39] bg-[#1e222d] p-4">
                <div className="flex items-center gap-3">
                  <Skeleton className="h-5 w-14" />
                  <Skeleton className="h-4 w-28" />
                </div>
                <div className="mt-2 flex gap-3">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-4 w-16" />
                </div>
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-[#2962ff]/20 bg-[#2962ff]/5 py-16">
            <p className="text-lg font-bold text-[#2962ff]">{"\u4eca\u65e5\u7a7a\u4ed3\u89c2\u671b"}</p>
            <p className="mt-2 text-sm text-[#787b86]">{"\u672a\u53d1\u73b0\u7b26\u5408\u7f6e\u4fe1\u5ea6\u9608\u503c\u7684\u6807\u7684\uff0c\u5efa\u8bae\u4fdd\u6301\u73b0\u91d1\u7b49\u5f85\u66f4\u597d\u673a\u4f1a"}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item, i) => (
              <RecCard key={item.ticker || i} item={item} rank={i + 1} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
