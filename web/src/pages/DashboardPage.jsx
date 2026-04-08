import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import Skeleton from "../components/Skeleton";
import PriceChange from "../components/PriceChange";
import { MarketBadge, DirectionBadge, StrategyBadge } from "../components/Badge";
import { Star, Eye, ArrowRight } from "lucide-react";

function IndexSkeleton() {
  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="rounded-xl bg-surface-1 p-6 ring-1 ring-white/5">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="mt-3 h-8 w-28" />
          <Skeleton className="mt-3 h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

function RecSkeleton() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="rounded-xl border border-border bg-white p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-4 w-24" />
            <div className="ml-auto flex gap-2">
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-4 w-20" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [indices, setIndices] = useState([]);
  const [recs, setRecs] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([api.marketOverview(), api.todayRecs()]).then(
      ([idxRes, recRes]) => {
        if (idxRes.status === "fulfilled") setIndices(idxRes.value || []);
        if (recRes.status === "fulfilled") setRecs(recRes.value);
        setLoading(false);
      },
    );
  }, []);

  const items = recs?.items || [];

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-light tracking-tight">仪表盘</h1>

      <section>
        <CardTitle>市场概览</CardTitle>
        {loading ? (
          <IndexSkeleton />
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {indices.map((idx, i) => {
              const isHK = idx.market === "hk_stock";
              const bg = isHK
                ? "bg-gradient-to-br from-amber-950/80 via-amber-900/40 to-surface-1"
                : "bg-gradient-to-br from-brand-950/80 via-brand-900/40 to-surface-1";
              return (
                <div
                  key={i}
                  className={`rounded-xl ${bg} p-8 shadow-lg ring-1 ring-white/5`}
                >
                  <div className="space-y-3">
                    <p className="text-base font-medium text-secondary tracking-wide">
                      {idx.name || idx.symbol}
                    </p>
                    <p className="text-4xl font-bold tabular-nums tracking-tight text-primary">
                      {idx.price?.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      }) ?? "--"}
                    </p>
                    <PriceChange value={idx.change_pct} size="xl" />
                  </div>
                </div>
              );
            })}
            {indices.length === 0 && (
              <Card className="col-span-full text-center text-sm text-secondary">
                暂无市场数据
              </Card>
            )}
          </div>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <CardTitle className="!mb-0">
            <Star size={16} className="mr-1 inline" />
            今日推荐
          </CardTitle>
          <div className="flex gap-3">
            <Link
              to="/recommendations/us"
              className="flex items-center gap-1 text-xs text-brand-400 hover:underline"
            >
              美股 <ArrowRight size={10} />
            </Link>
            <Link
              to="/recommendations/hk"
              className="flex items-center gap-1 text-xs text-[#D97706] hover:underline"
            >
              港股 <ArrowRight size={10} />
            </Link>
          </div>
        </div>

        {recs?.display_message && (
          <p className="mb-3 text-xs text-yellow-400">{recs.display_message}</p>
        )}

        {loading ? (
          <RecSkeleton />
        ) : items.length === 0 ? (
          <Card className="py-8 text-center text-sm text-secondary">
            今日暂无推荐发布
          </Card>
        ) : (
          <div className="space-y-2">
            {items.slice(0, 8).map((item, i) => {
              const isHK = item.market === "hk_stock";
              const curr = isHK ? "HK$" : "$";
              const conf = item.confidence || item.combined_score || item.score || 0;
              const confColor = conf >= 70 ? "#16A34A" : conf >= 50 ? "#8B7E74" : "#D97706";
              const confW = Math.max(0, Math.min(100, conf));
              return (
                <Link
                  key={i}
                  to={`/analysis?ticker=${item.ticker}&market=${item.market}`}
                  className="flex items-center gap-3 rounded-xl border border-border bg-white px-5 py-4 shadow-lg transition-all hover:border-border hover:bg-surface-2"
                >
                  {/* Left: ticker + badges */}
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-sm font-bold text-primary">{item.ticker}</span>
                    <span className="hidden truncate text-xs text-secondary sm:inline">{item.name}</span>
                    <MarketBadge market={item.market} />
                    <DirectionBadge direction={item.direction} />
                    <StrategyBadge strategy={item.strategy} />
                  </div>

                  {/* Center: price + confidence */}
                  <div className="ml-auto flex items-center gap-4">
                    <div className="hidden items-center gap-2 sm:flex">
                      <span className="text-sm font-semibold tabular-nums text-primary">
                        {curr}{item.price?.toFixed(2) ?? "--"}
                      </span>
                      <PriceChange value={item.change_pct} />
                    </div>

                    {/* Confidence mini bar */}
                    <div className="flex items-center gap-1.5">
                      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-surface-3">
                        <span className="block h-full rounded-full" style={{ width: `${confW}%`, background: confColor }} />
                      </span>
                      <span className="text-xs font-semibold tabular-nums" style={{ color: confColor }}>{Math.round(conf)}</span>
                    </div>

                    {/* SL/TP compact */}
                    {item.stop_loss && item.take_profit && (
                      <div className="hidden text-[10px] lg:flex lg:gap-2">
                        <span className="text-down/70">SL {item.stop_loss.toFixed(1)}</span>
                        <span className="text-up/70">TP {item.take_profit.toFixed(1)}</span>
                      </div>
                    )}

                    <Eye size={14} className="text-neutral-600" />
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
