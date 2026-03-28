import { Activity, TrendingUp, TrendingDown, Minus, Lightbulb } from "lucide-react";

function SentimentLabel({ label }) {
  const map = {
    bullish:  { text: "偏多", color: "#089981" },
    bearish:  { text: "偏空", color: "#f23645" },
    neutral:  { text: "中性", color: "#787b86" },
  };
  const info = map[label] || map.neutral;
  return (
    <span className="text-xs font-semibold px-2 py-0.5 rounded" style={{ color: info.color, background: info.color + "18" }}>
      {info.text}
    </span>
  );
}

function Dot({ color = "#089981" }) {
  return <span className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />;
}

function StatItem({ label, value, color }) {
  return (
    <span className="text-xs text-[#787b86]">
      {label}：<span className="font-semibold" style={{ color: color || "#d1d4dc" }}>{value}</span>
    </span>
  );
}

export default function MarketSentimentPanel({ data, market }) {
  if (!data) return null;

  const { sentiment, breadth, fear_greed: fg, headlines, analysis } = data;
  const fgValue = fg?.value != null ? Math.round(fg.value) : null;
  const fgLabel = fg?.label || (fgValue >= 75 ? "极度贪婪" : fgValue >= 60 ? "贪婪" : fgValue >= 40 ? "中性" : fgValue >= 25 ? "恐惧" : "极度恐惧");
  const fgColor = fgValue >= 60 ? "#089981" : fgValue >= 40 ? "#787b86" : "#f23645";

  const advN = breadth?.advance ?? 0;
  const decN = breadth?.decline ?? 0;
  const unchN = breadth?.unchanged ?? 0;
  const totalN = breadth?.total ?? 0;

  const bullPoints = [];
  const bearPoints = [];

  if (advN > decN) bullPoints.push("上涨家数多于下跌，多头占优");
  else if (decN > advN) bearPoints.push("下跌家数多于上涨，空头占优");

  if (fgValue != null && fgValue >= 60) bullPoints.push(`情绪评分${fgValue}分，市场偏乐观`);
  else if (fgValue != null && fgValue < 40) bearPoints.push(`情绪评分${fgValue}分，市场偏悲观`);

  if (sentiment?.positive > sentiment?.negative) bullPoints.push("正面新闻多于负面，情绪偏暖");
  else if (sentiment?.negative > sentiment?.positive) bearPoints.push("负面新闻多于正面，情绪偏冷");

  if ((headlines || []).length > 0) {
    bullPoints.push("有" + headlines.length + "条相关新闻，市场关注度高");
  }

  const riskLevel = fgValue >= 70 ? "中" : fgValue >= 40 ? "低" : "高";
  const strategyLevel = fgValue >= 60 ? "激进" : fgValue >= 40 ? "稳健" : "保守";
  const riskColor = riskLevel === "高" ? "#f23645" : riskLevel === "中" ? "#fb8c00" : "#089981";
  const strategyColor = strategyLevel === "激进" ? "#089981" : strategyLevel === "保守" ? "#f23645" : "#2962ff";

  return (
    <div className="space-y-3">
      {/* Market Sentiment Block */}
      <div className="rounded-lg border border-[#2a2e39] bg-[#1e222d] p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-semibold text-[#d1d4dc]">市场情绪</span>
              <SentimentLabel label={sentiment?.label} />
            </div>
            {fgValue != null && (
              <p className="text-2xl font-bold" style={{ color: fgColor }}>{fgLabel}</p>
            )}
            <p className="mt-1 text-xs text-[#787b86]">
              上涨 {advN} 家，下跌 {decN} 家
              {advN > decN ? "，多头占优" : decN > advN ? "，空头占优" : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-right">
            <StatItem label="上涨家数" value={advN} color="#089981" />
            <StatItem label="下跌家数" value={decN} color="#f23645" />
            {unchN > 0 && <StatItem label="平盘家数" value={unchN} />}
          </div>
        </div>
        {fgValue != null && (
          <p className="mt-2 text-xs text-[#787b86]">
            市场情绪评分{fgValue}分（{fgLabel}），
            {fgValue >= 60 ? "多头气氛浓厚，资金做多意愿较强" :
             fgValue >= 40 ? "市场情绪平稳，观望气氛偏重" :
             "恐慌情绪蔓延，谨慎为主"}。
          </p>
        )}
      </div>

      {/* Market Analysis Block */}
      <div className="rounded-lg border border-[#2a2e39] bg-[#1e222d] p-5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-[#d1d4dc]">市场分析</span>
          <div className="flex gap-2">
            <span className="rounded px-2 py-0.5 text-[11px] font-semibold"
              style={{ color: strategyColor, background: strategyColor + "18" }}>
              策略：{strategyLevel}
            </span>
            <span className="rounded px-2 py-0.5 text-[11px] font-semibold"
              style={{ color: riskColor, background: riskColor + "18" }}>
              风险：{riskLevel}
            </span>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-2">
          {bullPoints.map((p, i) => (
            <div key={"b"+i} className="flex items-start gap-2 text-xs text-[#d1d4dc]">
              <Dot color="#089981" />
              <span>{p}</span>
            </div>
          ))}
          {bearPoints.map((p, i) => (
            <div key={"r"+i} className="flex items-start gap-2 text-xs text-[#d1d4dc]">
              <Dot color="#f23645" />
              <span>{p}</span>
            </div>
          ))}
        </div>

        {/* Headlines */}
        {(headlines || []).length > 0 && (
          <div className="mt-3 space-y-1.5">
            {headlines.slice(0, 3).map((h, i) => (
              <a key={i} href={h.link} target="_blank" rel="noopener noreferrer"
                className="flex items-start gap-2 text-xs text-[#787b86] hover:text-brand-500 transition-colors">
                <Dot color="#363a45" />
                <span className="line-clamp-1">{h.title}</span>
              </a>
            ))}
          </div>
        )}

        {/* Operation Suggestion */}
        <div className="mt-4 rounded-lg border border-[#fb8c00]/25 bg-[#fb8c00]/5 p-3">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-[#fb8c00]">
            <Lightbulb size={13} />
            操作建议
          </div>
          <p className="text-xs leading-relaxed text-[#fb8c00]/80">
            {fgValue >= 60
              ? "市场情绪偏热，可适当参与强势标的，但注意控制仓位，防范追高风险。"
              : fgValue >= 40
                ? "市场情绪中性，建议以观望为主，精选个股，轻仓试探。"
                : "市场情绪偏冷，建议减仓防守，等待企稳信号后再入场。"}
          </p>
        </div>
      </div>
    </div>
  );
}
