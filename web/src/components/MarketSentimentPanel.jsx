import { Activity, TrendingUp, TrendingDown, Minus, Newspaper, BarChart3 } from "lucide-react";

const FEAR_GREED_COLORS = {
  "极度贪婪": { ring: "ring-green-400", text: "text-green-400", bg: "bg-green-500" },
  "贪婪": { ring: "ring-green-500/60", text: "text-green-400", bg: "bg-green-500" },
  "中性": { ring: "ring-yellow-500/60", text: "text-yellow-400", bg: "bg-yellow-500" },
  "恐惧": { ring: "ring-red-500/60", text: "text-red-400", bg: "bg-red-500" },
  "极度恐惧": { ring: "ring-red-400", text: "text-red-400", bg: "bg-red-500" },
};

function FearGreedGauge({ value, label }) {
  const colors = FEAR_GREED_COLORS[label] || FEAR_GREED_COLORS["中性"];
  const angle = (value / 100) * 180 - 90;

  return (
    <div className="flex flex-col items-center">
      <div className="relative h-20 w-40 overflow-hidden">
        <svg viewBox="0 0 120 60" className="h-full w-full">
          <path
            d="M 10 55 A 50 50 0 0 1 110 55"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            className="text-surface-3"
          />
          <path
            d="M 10 55 A 50 50 0 0 1 110 55"
            fill="none"
            stroke="url(#gauge-gradient)"
            strokeWidth="8"
            strokeDasharray={`${(value / 100) * 157} 157`}
          />
          <defs>
            <linearGradient id="gauge-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#ef4444" />
              <stop offset="25%" stopColor="#f97316" />
              <stop offset="50%" stopColor="#eab308" />
              <stop offset="75%" stopColor="#22c55e" />
              <stop offset="100%" stopColor="#16a34a" />
            </linearGradient>
          </defs>
          <line
            x1="60"
            y1="55"
            x2={60 + 35 * Math.cos((angle * Math.PI) / 180)}
            y2={55 - 35 * Math.abs(Math.sin((angle * Math.PI) / 180))}
            stroke="white"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <circle cx="60" cy="55" r="3" fill="white" />
        </svg>
      </div>
      <div className="mt-1 text-center">
        <span className={`text-2xl font-bold ${colors.text}`}>{value}</span>
        <p className={`text-sm font-semibold ${colors.text}`}>{label}</p>
      </div>
    </div>
  );
}

function BreadthBar({ advance, decline, unchanged, total }) {
  if (!total || total === 0) return null;
  const aPct = (advance / total) * 100;
  const dPct = (decline / total) * 100;

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-[11px] text-gray-400">
        <span className="text-green-400">上涨 {advance}</span>
        <span>平盘 {unchanged}</span>
        <span className="text-red-400">下跌 {decline}</span>
      </div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full">
        <div className="bg-green-500" style={{ width: `${aPct}%` }} />
        <div className="bg-gray-600" style={{ width: `${100 - aPct - dPct}%` }} />
        <div className="bg-red-500" style={{ width: `${dPct}%` }} />
      </div>
    </div>
  );
}

function SentimentLabel({ label }) {
  const map = {
    bullish: { icon: TrendingUp, text: "偏多", cls: "text-green-400" },
    bearish: { icon: TrendingDown, text: "偏空", cls: "text-red-400" },
    neutral: { icon: Minus, text: "中性", cls: "text-yellow-400" },
  };
  const info = map[label] || map.neutral;
  const Icon = info.icon;
  return (
    <span className={`flex items-center gap-1 text-sm font-semibold ${info.cls}`}>
      <Icon size={14} /> {info.text}
    </span>
  );
}

export default function MarketSentimentPanel({ data, market }) {
  if (!data) return null;

  const { sentiment, breadth, fear_greed: fg, headlines } = data;

  return (
    <section className="rounded-xl border border-surface-3 bg-surface-1 p-5">
      <div className="mb-4 flex items-center gap-2">
        <Activity size={16} className="text-brand-400" />
        <span className="text-sm font-bold text-gray-200">市场情绪分析</span>
        <SentimentLabel label={sentiment?.label} />
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Fear & Greed gauge */}
        <div className="flex flex-col items-center justify-center rounded-lg bg-surface-0/50 p-4">
          <p className="mb-2 text-xs font-semibold text-gray-400">贪婪恐惧指数</p>
          <FearGreedGauge value={fg?.value ?? 50} label={fg?.label ?? "中性"} />
        </div>

        {/* Breadth + stats */}
        <div className="flex flex-col justify-center space-y-4 rounded-lg bg-surface-0/50 p-4">
          <div>
            <p className="mb-2 text-xs font-semibold text-gray-400">
              <BarChart3 size={12} className="mr-1 inline" />
              涨跌家数
            </p>
            <BreadthBar
              advance={breadth?.advance ?? 0}
              decline={breadth?.decline ?? 0}
              unchanged={breadth?.unchanged ?? 0}
              total={breadth?.total ?? 0}
            />
          </div>
          <div className="grid grid-cols-2 gap-3 text-center">
            <div>
              <p className="text-[11px] text-gray-500">多空信号数</p>
              <p className="text-sm">
                <span className="font-semibold text-green-400">{sentiment?.positive ?? 0}</span>
                {" / "}
                <span className="font-semibold text-red-400">{sentiment?.negative ?? 0}</span>
              </p>
            </div>
            <div>
              <p className="text-[11px] text-gray-500">情绪评分</p>
              <p className={`text-sm font-bold ${
                (sentiment?.score ?? 0) > 0 ? "text-green-400" : (sentiment?.score ?? 0) < 0 ? "text-red-400" : "text-yellow-400"
              }`}>
                {sentiment?.score != null ? (sentiment.score > 0 ? "+" : "") + sentiment.score.toFixed(2) : "--"}
              </p>
            </div>
          </div>
        </div>

        {/* Headlines */}
        <div className="rounded-lg bg-surface-0/50 p-4">
          <p className="mb-2 text-xs font-semibold text-gray-400">
            <Newspaper size={12} className="mr-1 inline" />
            热点新闻
          </p>
          <div className="space-y-2">
            {(headlines || []).slice(0, 4).map((h, i) => (
              <a
                key={i}
                href={h.link}
                target="_blank"
                rel="noopener noreferrer"
                className="block truncate text-xs text-gray-300 transition-colors hover:text-brand-400"
                title={h.title}
              >
                <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-brand-500" />
                {h.title}
              </a>
            ))}
            {(!headlines || headlines.length === 0) && (
              <p className="text-xs text-gray-600">暂无新闻</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
