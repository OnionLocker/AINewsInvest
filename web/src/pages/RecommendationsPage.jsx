import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import PriceChange from "../components/PriceChange";
import RecCard from "../components/RecCard";
import MarketSentimentPanel from "../components/MarketSentimentPanel";
import Skeleton from "../components/Skeleton";
import { Calendar, Clock, Trophy, TrendingUp, TrendingDown } from "lucide-react";

const MARKET_CFG = {
  us: {
    title: "\u7f8e\u80a1\u63a8\u8350",
    mkt: "us_stock",
    indexFilter: (idx) => idx.market === "us_stock",
  },
  hk: {
    title: "\u6e2f\u80a1\u63a8\u8350",
    mkt: "hk_stock",
    indexFilter: (idx) => idx.market === "hk_stock",
  },
};

function looksMojibake(text) {
  if (!text) return false;
  const s = String(text);
  return s.includes("\uFFFD") || s.includes("\u00C3") || s.includes("\u00E2") || /[\u95BA\u7F01\u95C1\u5A75\u7134\u6FDE\u923A]/.test(s);
}

function normalizeIndexName(idx) {
  const raw = idx?.name || idx?.symbol || "";
  if (!looksMojibake(raw)) return raw;
  if (idx?.market === "hk_stock") return "\u6052\u751f\u6307\u6570";
  const price = Number(idx?.price || 0);
  if (price > 30000) return "\u9053\u743c\u65af";
  if (price > 10000) return "\u7eb3\u65af\u8fbe\u514b";
  return "\u6807\u666e500";
}

function IndexCard({ idx }) {
  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <p className="text-xs text-secondary">{normalizeIndexName(idx)}</p>
      <p className="mt-1.5 text-2xl font-semibold tabular-nums text-primary">
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


function WinRateBanner({ market }) {
  const [wr, setWr] = useState(null);
  useEffect(() => {
    api.winRateSummary().then(setWr).catch(() => {});
  }, []);
  if (!wr) return null;
  const mkt = market === "hk" ? "hk_stock" : "us_stock";
  const d = wr[mkt];
  if (!d) return null;
  const all = d.all || {};
  if (!all.total_evaluated) return null;
  const rate = all.win_rate || 0;
  const rateColor = rate >= 60 ? "#16A34A" : rate >= 45 ? "#D97706" : "#DC2626";
  const avgRet = all.avg_return_pct || 0;
  const retColor = avgRet >= 0 ? "#16A34A" : "#DC2626";
  return (
    <Link to="/win-rate"
      className="flex items-center gap-4 rounded-2xl border border-border px-5 py-3 shadow-lg transition-colors hover:border-border">
      <div className="flex items-center gap-2">
        <Trophy size={16} className="text-[#D97706]" />
        <span className="text-sm font-bold text-primary">{"\u7cfb\u7edf\u80dc\u7387"}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-lg font-extrabold tabular-nums" style={{ color: rateColor }}>{rate.toFixed(1)}%</span>
        <span className="text-xs text-secondary">({all.wins || 0}W / {all.total_evaluated}T)</span>
      </div>
      <div className="h-4 w-px bg-border" />
      <div className="flex items-center gap-1.5">
        {avgRet >= 0 ? <TrendingUp size={14} style={{ color: retColor }} /> : <TrendingDown size={14} style={{ color: retColor }} />}
        <span className="text-sm font-bold tabular-nums" style={{ color: retColor }}>
          {avgRet >= 0 ? "+" : ""}{avgRet.toFixed(2)}%
        </span>
        <span className="text-xs text-secondary">{"\u5e73\u5747\u6536\u76ca"}</span>
      </div>
      {all.pending > 0 && (
        <>
          <div className="h-4 w-px bg-border" />
          <span className="text-xs text-secondary">{all.pending} {"\u5f85\u8bc4\u4f30"}</span>
        </>
      )}
      <span className="ml-auto text-xs text-secondary hover:text-brand">{"\u67e5\u770b\u8be6\u60c5 \u2192"}</span>
    </Link>
  );
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
  const [updatedAtBj, setUpdatedAtBj] = useState("");

  function markUpdatedNow() {
    const ts = new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      hour12: false,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date());
    setUpdatedAtBj(ts);
  }

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
      markUpdatedNow();
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
      markUpdatedNow();
    } catch {
      setDetail(null);
    }
  }

  const items = detail?.items || today?.items || [];
  const viewingDate = detail ? detail.run?.ref_date : "\u4eca\u65e5";

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <h1 className="text-3xl font-light text-primary">{cfg.title}</h1>
        {updatedAtBj && (
          <p className="text-xs text-secondary">
            {"\u66f4\u65b0\u4e8e\u5317\u4eac\u65f6\u95f4 "} {updatedAtBj}
          </p>
        )}
      </div>

      {/* Market indices */}
      <section>
        {loading ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {[1,2,3].map(i => (
              <div key={i} className="rounded-xl border border-border bg-white p-4">
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
        <div className="rounded-2xl border border-border p-5 shadow-lg">
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

      {/* Win rate banner */}
      <WinRateBanner market={market} />

      {/* Display message */}
      {today?.display_message && !detail && (
        <div className="flex items-center gap-2 rounded-xl border border-border bg-white px-4 py-3 text-xs text-secondary">
          <Clock size={14} />
          {today.display_message}
        </div>
      )}

      {/* History bar + Rec header */}
      <div className="flex items-center gap-3">
        <Calendar size={13} className="text-secondary" />
        <p className="text-xs font-medium text-secondary">{"\u5386\u53f2\u8bb0\u5f55"}</p>
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-thin">
          <button
            onClick={() => setDetail(null)}
            className={`shrink-0 rounded-lg px-2.5 py-1 text-xs transition-colors ${
              !detail
                ? "bg-surface-3 font-semibold text-brand"
                : "text-secondary hover:text-primary"
            }`}
          >
            {"\u4eca\u65e5\u63a8\u8350"}
          </button>
          {history.map((h) => (
            <button
              key={h.id || h.ref_date}
              onClick={() => loadDate(h.ref_date)}
              className={`shrink-0 rounded-lg px-2.5 py-1 text-xs transition-colors ${
                detail?.run?.ref_date === h.ref_date
                  ? "bg-brand/10 font-semibold text-brand"
                  : "text-secondary hover:text-primary"
              }`}
            >
              {h.ref_date}
              <span className="ml-1 text-secondary">{h.published_count ?? h.result_count}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Recommendations - full width */}
      <div>
        <div className="mb-3 flex items-center gap-2">
          <p className="text-sm font-semibold text-primary">{"\u63a8\u8350\u5217\u8868"}</p>
          <span className="text-xs text-secondary">
            {items.length} {"\u53ea"}
          </span>
          {items.length > 0 && (() => {
            const h = items.filter(i => i.quality_tier === "high").length;
            const m = items.filter(i => i.quality_tier === "medium").length;
            const l = items.filter(i => i.quality_tier === "low").length;
            const parts = [];
            if (h) parts.push(`${h} \u9ad8\u4fe1\u5fc3`);
            if (m) parts.push(`${m} \u4e2d\u7b49`);
            if (l) parts.push(`${l} \u89c2\u671b`);
            return parts.length > 0 ? (
              <span className="text-xs text-secondary">({parts.join(" / ")})</span>
            ) : null;
          })()}
          {items.length > 0 && (() => {
            const st = items.filter(i => i.strategy !== "swing").length;
            const sw = items.filter(i => i.strategy === "swing").length;
            if (st && sw) {
              return <span className="text-xs text-secondary">{"\u00b7"} {"\u77ed\u7ebf"} {st} / {"\u6ce2\u6bb5"} {sw}</span>;
            }
            return null;
          })()}
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1,2,3].map(i => (
              <div key={i} className="rounded-xl border border-border bg-white p-4">
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
          <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-white py-16 shadow-lg">
            <p className="text-lg font-bold text-brand">{"\u4eca\u65e5\u7a7a\u4ed3\u89c2\u671b"}</p>
            <p className="mt-2 text-sm text-secondary">{"\u672a\u53d1\u73b0\u7b26\u5408\u7f6e\u4fe1\u5ea6\u9608\u503c\u7684\u6807\u7684\uff0c\u5efa\u8bae\u4fdd\u6301\u73b0\u91d1\u7b49\u5f85\u66f4\u597d\u673a\u4f1a"}</p>
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
