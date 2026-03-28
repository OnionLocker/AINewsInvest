import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import { PageLoader } from "../components/Spinner";
import { MarketBadge, DirectionBadge, StrategyBadge } from "../components/Badge";
import { Calendar, Eye } from "lucide-react";

export default function RecommendationsPage() {
  const [today, setToday] = useState(null);
  const [history, setHistory] = useState([]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([api.todayRecs(), api.recHistory(30)]).then(
      ([tRes, hRes]) => {
        if (tRes.status === "fulfilled") setToday(tRes.value);
        if (hRes.status === "fulfilled") setHistory(hRes.value || []);
        setLoading(false);
      },
    );
  }, []);

  async function loadDate(date) {
    try {
      const d = await api.recByDate(date);
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
      <h1 className="text-xl font-bold">推荐列表</h1>

      <div className="flex gap-6">
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

        <div className="flex-1">
          <div className="mb-3 flex items-center gap-2">
            <CardTitle className="!mb-0">{viewingDate}</CardTitle>
            {today?.display_message && !detail && (
              <span className="text-xs text-yellow-400">
                {today.display_message}
              </span>
            )}
          </div>

          {items.length === 0 ? (
            <Card className="py-10 text-center text-sm text-gray-500">
              该日期暂无推荐
            </Card>
          ) : (
            <div className="space-y-2">
              {items.map((item, i) => (
                <Card
                  key={i}
                  className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold">
                          {item.ticker}
                        </span>
                        <MarketBadge market={item.market} />
                        <DirectionBadge direction={item.direction} />
                        <StrategyBadge strategy={item.strategy} />
                      </div>
                      <p className="mt-0.5 text-xs text-gray-500">{item.name}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 text-xs text-gray-400">
                    <span>
                      评分:{" "}
                      <b className="text-gray-200">{item.score?.toFixed(1)}</b>
                    </span>
                    <span>入场: ${item.entry_price?.toFixed(2) ?? "--"}</span>
                    <span>止损: ${item.stop_loss?.toFixed(2) ?? "--"}</span>
                    <span>止盈: ${item.take_profit?.toFixed(2) ?? "--"}</span>
                    <Link
                      to={`/analysis?ticker=${item.ticker}&market=${item.market}`}
                      className="text-brand-400 hover:underline"
                    >
                      <Eye size={14} />
                    </Link>
                  </div>
                </Card>
              ))}
            </div>
          )}

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
