import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import { PageLoader } from "../components/Spinner";
import PriceChange from "../components/PriceChange";
import { MarketBadge, DirectionBadge, StrategyBadge } from "../components/Badge";
import { TrendingUp, Star, Eye } from "lucide-react";

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

  if (loading) return <PageLoader />;

  const items = recs?.items || [];

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">仪表盘</h1>

      <section>
        <CardTitle>市场概览</CardTitle>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {indices.map((idx, i) => {
            const isHK = idx.market === "hk_stock";
            const bg = isHK
              ? "bg-gradient-to-br from-amber-950/80 via-amber-900/40 to-surface-1"
              : "bg-gradient-to-br from-brand-950/80 via-brand-900/40 to-surface-1";
            return (
              <div
                key={i}
                className={`rounded-xl ${bg} p-6 shadow-lg ring-1 ring-white/5`}
              >
                <div className="space-y-3">
                  <p className="text-base font-semibold text-gray-300 tracking-wide">
                    {idx.name || idx.symbol}
                  </p>
                  <p className="text-3xl font-bold tabular-nums tracking-tight text-white">
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
            <Card className="col-span-full text-center text-sm text-gray-500">
              暂无市场数据
            </Card>
          )}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <CardTitle className="!mb-0">
            <Star size={16} className="mr-1 inline" />
            今日推荐
          </CardTitle>
          <Link
            to="/recommendations/us"
            className="text-xs text-brand-400 hover:underline"
          >
            查看全部
          </Link>
        </div>

        {recs?.display_message && (
          <p className="mb-3 text-xs text-yellow-400">{recs.display_message}</p>
        )}

        {items.length === 0 ? (
          <Card className="py-8 text-center text-sm text-gray-500">
            今日暂无推荐发布
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {items.slice(0, 6).map((item, i) => (
              <Card key={i} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-semibold">
                      {item.ticker}
                    </span>
                    <MarketBadge market={item.market} />
                  </div>
                  <div className="flex gap-1">
                    <DirectionBadge direction={item.direction} />
                    <StrategyBadge strategy={item.strategy} />
                  </div>
                </div>
                <p className="text-xs text-gray-400">{item.name}</p>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-500">
                    评分: {item.score?.toFixed(1) ?? "--"}
                  </span>
                  <span className="text-gray-500">
                    入场: ${item.entry_price?.toFixed(2) ?? "--"}
                  </span>
                </div>
                {item.recommendation_reason && (
                  <p className="line-clamp-2 text-xs text-gray-500">
                    {item.recommendation_reason}
                  </p>
                )}
                <Link
                  to={`/analysis?ticker=${item.ticker}&market=${item.market}`}
                  className="inline-flex items-center gap-1 text-xs text-brand-400 hover:underline"
                >
                  <Eye size={12} /> 详情
                </Link>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
