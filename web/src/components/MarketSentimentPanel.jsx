import { Lightbulb } from "lucide-react";

function SentimentLabel({ label }) {
  const map = {
    bullish:  { text: "偏多", color: "#16A34A" },
    bearish:  { text: "偏空", color: "#DC2626" },
    neutral:  { text: "中性", color: "#8B7E74" },
  };
  const info = map[label] || map.neutral;
  return (
    <span className="rounded border border-border px-2.5 py-0.5 text-sm font-bold" style={{ color: info.color, background: info.color + "18" }}>
      {info.text}
    </span>
  );
}

function Dot({ color = "#16A34A" }) {
  return <span className="mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />;
}

function StatItem({ label, value, color }) {
  return (
    <span className="text-base font-medium text-secondary">
      {label}{"："}<span className="font-bold" style={{ color: color || "#e2e8f0" }}>{value}</span>
    </span>
  );
}

export default function MarketSentimentPanel({ data, market }) {
  if (!data) return null;

  const { sentiment, breadth, breadth_scope, fear_greed: fg, headlines, analysis, vix } = data;
  const fgValue = fg?.value != null ? Math.round(fg.value) : null;
  const fgLabel = fg?.label || (fgValue >= 75 ? "极度贪婪" : fgValue >= 60 ? "贪婪" : fgValue >= 40 ? "中性" : fgValue >= 25 ? "恐惧" : "极度恐惧");
  const fgColor = fgValue >= 60 ? "#16A34A" : fgValue >= 40 ? "#8B7E74" : "#DC2626";

  const vixValue = vix != null ? Number(vix) : null;
  const vixColor = vixValue >= 30 ? "#DC2626" : vixValue >= 20 ? "#D97706" : "#16A34A";
  const vixLabel = vixValue >= 30 ? "恐慌" : vixValue >= 20 ? "谨慎" : "平静";

  const advN = breadth?.advance ?? 0;
  const decN = breadth?.decline ?? 0;
  const unchN = breadth?.unchanged ?? 0;
  const totalN = breadth?.total ?? 0;
  const scopeLabel = breadth_scope || (market === "hk" ? "恒指+恒生科技成分股" : "标普500成分股");

  const bullPoints = [];
  const bearPoints = [];

  if (advN > decN) bullPoints.push("上涨家数多于下跌，多头占优");
  else if (decN > advN) bearPoints.push("下跌家数多于上涨，空头占优");

  if (fgValue != null && fgValue >= 60) bullPoints.push(`情绪评分${fgValue}分，市场偏乐观`);
  else if (fgValue != null && fgValue < 40) bearPoints.push(`情绪评分${fgValue}分，市场偏悲观`);

  if (sentiment?.positive > sentiment?.negative) bullPoints.push("正面新闻多于负面，情绪偏暖");
  else if (sentiment?.negative > sentiment?.positive) bearPoints.push("负面新闻多于正面，情绪偏冷");

  if (vixValue != null) {
    if (vixValue < 20) bullPoints.push(`VIX恐慌指数${vixValue}，市场平静`);
    else if (vixValue >= 30) bearPoints.push(`VIX恐慌指数${vixValue}，市场恐慌`);
    else bearPoints.push(`VIX恐慌指数${vixValue}，市场偏谨慎`);
  }

  if ((headlines || []).length > 0) {
    bullPoints.push("有" + headlines.length + "条相关新闻，市场关注度高");
  }

  const riskLevel = fgValue >= 70 ? "中" : fgValue >= 40 ? "低" : "高";
  const strategyLevel = fgValue >= 60 ? "激进" : fgValue >= 40 ? "稳健" : "保守";
  const riskColor = riskLevel === "高" ? "#DC2626" : riskLevel === "中" ? "#D97706" : "#16A34A";
  const strategyColor = strategyLevel === "激进" ? "#16A34A" : strategyLevel === "保守" ? "#DC2626" : "#2563EB";

  return (
    <div className="space-y-3">
      {/* Market Sentiment Block */}
      <div className="rounded-2xl border border-border bg-white p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="text-base font-bold text-primary">{"市场情绪"}</span>
              <SentimentLabel label={sentiment?.label} />
            </div>
            {fgValue != null && (
              <p className="text-3xl font-extrabold" style={{ color: fgColor }}>{fgLabel}</p>
            )}
            <p className="mt-1 text-base font-medium text-secondary">
              {scopeLabel}{"("}{totalN}{"只）："}{"上涨"} {advN} {"家、下跌"} {decN} {"家"}
              {unchN > 0 ? `、平盘 ${unchN} 家` : ""}
              {advN > decN ? "，多头占优" : decN > advN ? "，空头占优" : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-right">
            <StatItem label={"上涨家数"} value={advN} color="#16A34A" />
            <StatItem label={"下跌家数"} value={decN} color="#DC2626" />
            {unchN > 0 && <StatItem label={"平盘家数"} value={unchN} />}
            {vixValue != null && (
              <StatItem label={"VIX恐慌指数"} value={`${vixValue} (${vixLabel})`} color={vixColor} />
            )}
          </div>
        </div>
        {fgValue != null && (
          <p className="mt-2 text-base font-medium text-secondary">
            {"市场情绪评分"}{fgValue}{"分（"}{fgLabel}{"），"}
            {fgValue >= 60 ? "多头气氛浓厚，资金做多意愿较强" :
             fgValue >= 40 ? "市场情绪平稳，观望气氛偏重" :
             "恐慌情绪蔓延，谨慎为主"}{"。"}
          </p>
        )}
      </div>

      {/* Market Analysis Block */}
      <div className="rounded-2xl border border-border bg-white p-5 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-base font-bold text-primary">{"市场分析"}</span>
          <div className="flex gap-2">
            <span className="rounded border border-border px-2.5 py-1 text-sm font-bold"
              style={{ color: strategyColor, background: strategyColor + "18" }}>
              {"策略："}{strategyLevel}
            </span>
            <span className="rounded border border-border px-2.5 py-1 text-sm font-bold"
              style={{ color: riskColor, background: riskColor + "18" }}>
              {"风险："}{riskLevel}
            </span>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-2">
          {bullPoints.map((p, i) => (
            <div key={"b"+i} className="flex items-start gap-2 text-base font-medium text-primary">
              <Dot color="#16A34A" />
              <span>{p}</span>
            </div>
          ))}
          {bearPoints.map((p, i) => (
            <div key={"r"+i} className="flex items-start gap-2 text-base font-medium text-primary">
              <Dot color="#DC2626" />
              <span>{p}</span>
            </div>
          ))}
        </div>

        {/* Headlines */}
        {(headlines || []).length > 0 && (
          <div className="mt-3 space-y-1.5">
            {headlines.slice(0, 3).map((h, i) => (
              <a key={i} href={h.link} target="_blank" rel="noopener noreferrer"
                className="flex items-start gap-2 text-sm font-medium text-secondary transition-colors hover:text-brand">
                <Dot color="#64748b" />
                <span className="line-clamp-1">{h.title}</span>
              </a>
            ))}
          </div>
        )}

        {/* Operation Suggestion */}
        <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
          <div className="mb-1 flex items-center gap-1.5 text-base font-bold text-amber-400">
            <Lightbulb size={16} />
            {"操作建议"}
          </div>
          <p className="text-base font-medium leading-relaxed text-amber-400/80">
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
