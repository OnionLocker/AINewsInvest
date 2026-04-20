import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import PriceChange from "../components/PriceChange";
import RecCard from "../components/RecCard";
import MarketSentimentPanel from "../components/MarketSentimentPanel";
import Skeleton from "../components/Skeleton";
import { Calendar, Clock, Trophy, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";

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

// v11: Macro event advisory banner (FOMC / CPI / NFP / PCE).
// Red alert on day-of critical, amber warning on day-before, subtle info
// chip for upcoming events within 5 days. US only.
function MacroAdvisoryBanner({ advisory }) {
  if (!advisory || advisory.market !== "us_stock") return null;
  const today = advisory.today || [];
  const tomorrow = advisory.tomorrow || [];
  const upcoming = advisory.upcoming;

  const labelForCode = (code) => ({
    FOMC: "\u8054\u50a8\u5229\u7387\u51b3\u8bae",
    CPI: "CPI \u901a\u80c0\u6570\u636e",
    PCE: "PCE \u901a\u80c0\u6570\u636e",
    NFP: "\u975e\u519c\u5c31\u4e1a",
  }[code] || code);

  const todayCritical = today.filter((e) => e.severity === "critical");
  if (todayCritical.length > 0) {
    const names = todayCritical.map((e) => labelForCode(e.code)).join(" / ");
    return (
      <div className="flex items-start gap-2 rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-600" />
        <div>
          <p className="font-bold text-red-700">{"\u4eca\u65e5\u91cd\u5927\u5b8f\u89c2\u4e8b\u4ef6\uff1a"}{names}</p>
          <p className="mt-0.5 text-xs text-red-700/80">
            {"\u5e02\u573a\u6ce2\u52a8\u7387\u5c06\u6025\u5267\u653e\u5927\uff0cATR-based \u6b62\u635f\u53ef\u80fd\u5931\u6548\u3002\u5df2\u81ea\u52a8\u5347\u7ea7 regime \u4e3a cautious\uff0c\u5efa\u8bae\u51cf\u534a\u6301\u4ed3\u6216\u7b49\u5f85\u6570\u636e\u516c\u5e03\u540e\u518d\u8fdb\u573a\u3002"}
          </p>
        </div>
      </div>
    );
  }

  const tomorrowCritical = tomorrow.filter((e) => e.severity === "critical");
  if (tomorrowCritical.length > 0) {
    const names = tomorrowCritical.map((e) => labelForCode(e.code)).join(" / ");
    return (
      <div className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-600" />
        <div>
          <p className="font-bold text-amber-700">{"\u660e\u65e5\u91cd\u5927\u5b8f\u89c2\u4e8b\u4ef6\uff1a"}{names}</p>
          <p className="mt-0.5 text-xs text-amber-700/80">
            {"\u7cfb\u7edf\u5df2\u5c06\u4eca\u65e5\u63a8\u8350\u6570\u91cf\u8150\u65a9\uff08\u5e02\u573a\u5e38\u5728\u91cd\u8981\u6570\u636e\u524d\u5065\u884c\u60c5\u6216\u6551\u5047\u7a81\u7834\uff09\u3002"}
          </p>
        </div>
      </div>
    );
  }

  if (upcoming && upcoming.days_until > 1 && upcoming.days_until <= 5) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border bg-white px-4 py-2 text-xs text-secondary">
        <Calendar size={13} />
        <span>
          {upcoming.days_until} {"\u5929\u540e\uff1a"}
          {labelForCode(upcoming.code)} ({upcoming.date})
        </span>
      </div>
    );
  }

  return null;
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
  const [strategyTab, setStrategyTab] = useState("short_term");

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

  const shortItems = items.filter(i => i.strategy !== "swing");
  const swingItems = items.filter(i => i.strategy === "swing");
  const visibleItems = strategyTab === "short_term" ? shortItems : swingItems;

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

      {/* v11: Macro event advisory (US only) */}
      <MacroAdvisoryBanner advisory={(detail || today)?.macro_advisory} />

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
        {/* Strategy tabs */}
        <div className="mb-3 flex items-center gap-2">
          <button
            onClick={() => setStrategyTab("short_term")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              strategyTab === "short_term"
                ? "bg-brand/10 text-brand font-semibold"
                : "text-secondary hover:text-primary hover:bg-surface-3"
            }`}
          >
            {"\u77ed\u7ebf\u63a8\u8350"}
            {shortItems.length > 0 && (
              <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-xs ${
                strategyTab === "short_term" ? "bg-brand/20 text-brand" : "bg-surface-3 text-secondary"
              }`}>{shortItems.length}</span>
            )}
          </button>
          <button
            onClick={() => setStrategyTab("swing")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              strategyTab === "swing"
                ? "bg-brand/10 text-brand font-semibold"
                : "text-secondary hover:text-primary hover:bg-surface-3"
            }`}
          >
            {"\u6ce2\u6bb5\u63a8\u8350"}
            {swingItems.length > 0 && (
              <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-xs ${
                strategyTab === "swing" ? "bg-brand/20 text-brand" : "bg-surface-3 text-secondary"
              }`}>{swingItems.length}</span>
            )}
          </button>
          {visibleItems.length > 0 && (() => {
            const h = visibleItems.filter(i => i.quality_tier === "high").length;
            const m = visibleItems.filter(i => i.quality_tier === "medium").length;
            const l = visibleItems.filter(i => i.quality_tier === "low").length;
            const parts = [];
            if (h) parts.push(`${h} \u9ad8\u4fe1\u5fc3`);
            if (m) parts.push(`${m} \u4e2d\u7b49`);
            if (l) parts.push(`${l} \u89c2\u671b`);
            return parts.length > 0 ? (
              <span className="text-xs text-secondary">({parts.join(" / ")})</span>
            ) : null;
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
          (() => {
            const state = (detail || today)?.empty_state;
            if (state === "pipeline_not_run_today") {
              return (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-amber-200 bg-amber-50 py-16 shadow-lg">
                  <p className="text-lg font-bold text-amber-700">{"\u4eca\u65e5\u7ba1\u7ebf\u5c1a\u672a\u8fd0\u884c"}</p>
                  <p className="mt-2 text-sm text-amber-700/80">
                    {"\u7cfb\u7edf\u4f1a\u5728\u5e02\u573a\u5f00\u76d8\u524d\u81ea\u52a8\u8fd0\u884c\uff0c\u8bf7\u7a0d\u540e\u5237\u65b0\u3002\u5f53\u524d\u5c55\u793a\u6700\u8fd1\u4e00\u6b21\u7684\u63a8\u8350\u4ec5\u4f9b\u53c2\u8003"}
                  </p>
                </div>
              );
            }
            if (state === "no_data") {
              return (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-white py-16 shadow-lg">
                  <p className="text-lg font-bold text-secondary">{"\u6682\u65e0\u63a8\u8350\u6570\u636e"}</p>
                  <p className="mt-2 text-sm text-secondary">{"\u7ba1\u7ebf\u8fd8\u672a\u4ea7\u51fa\u8fc7\u4efb\u4f55\u63a8\u8350\uff0c\u8bf7\u7b49\u5f85\u6216\u624b\u52a8\u89e6\u53d1"}</p>
                </div>
              );
            }
            // no_signals_today or fallback
            return (
              <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-white py-16 shadow-lg">
                <p className="text-lg font-bold text-brand">{"\u4eca\u65e5\u7a7a\u4ed3\u89c2\u671b"}</p>
                <p className="mt-2 text-sm text-secondary">{"\u672a\u53d1\u73b0\u7b26\u5408\u7f6e\u4fe1\u5ea6\u9608\u503c\u7684\u6807\u7684\uff0c\u5efa\u8bae\u4fdd\u6301\u73b0\u91d1\u7b49\u5f85\u66f4\u597d\u673a\u4f1a"}</p>
              </div>
            );
          })()
        ) : visibleItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-white py-12 shadow-lg">
            <p className="text-base font-medium text-secondary">
              {strategyTab === "short_term" ? "\u4eca\u65e5\u65e0\u77ed\u7ebf\u63a8\u8350" : "\u4eca\u65e5\u65e0\u6ce2\u6bb5\u63a8\u8350"}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {visibleItems.map((item, i) => (
              <RecCard key={item.ticker || i} item={item} rank={i + 1} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
