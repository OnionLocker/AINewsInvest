import { Lightbulb } from "lucide-react";

function SentimentLabel({ label }) {
  const map = {
    bullish:  { text: "\u504f\u591a", color: "#34d399" },
    bearish:  { text: "\u504f\u7a7a", color: "#fb7185" },
    neutral:  { text: "\u4e2d\u6027", color: "#94a3b8" },
  };
  const info = map[label] || map.neutral;
  return (
    <span className="rounded border border-slate-800/60 px-2.5 py-0.5 text-sm font-bold" style={{ color: info.color, background: info.color + "18" }}>
      {info.text}
    </span>
  );
}

function Dot({ color = "#34d399" }) {
  return <span className="mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />;
}

function StatItem({ label, value, color }) {
  return (
    <span className="text-base font-medium text-slate-400">
      {label}{"\uFF1A"}<span className="font-bold" style={{ color: color || "#e2e8f0" }}>{value}</span>
    </span>
  );
}

export default function MarketSentimentPanel({ data, market }) {
  if (!data) return null;

  const { sentiment, breadth, breadth_scope, fear_greed: fg, headlines, analysis } = data;
  const fgValue = fg?.value != null ? Math.round(fg.value) : null;
  const fgLabel = fg?.label || (fgValue >= 75 ? "\u6781\u5ea6\u8d2a\u5a6a" : fgValue >= 60 ? "\u8d2a\u5a6a" : fgValue >= 40 ? "\u4e2d\u6027" : fgValue >= 25 ? "\u6050\u60e7" : "\u6781\u5ea6\u6050\u60e7");
  const fgColor = fgValue >= 60 ? "#34d399" : fgValue >= 40 ? "#94a3b8" : "#fb7185";

  const advN = breadth?.advance ?? 0;
  const decN = breadth?.decline ?? 0;
  const unchN = breadth?.unchanged ?? 0;
  const totalN = breadth?.total ?? 0;
  const scopeLabel = breadth_scope || (market === "hk" ? "\u6052\u6307+\u6052\u751f\u79d1\u6280\u6210\u5206\u80a1" : "\u6807\u666e500\u6210\u5206\u80a1");

  const bullPoints = [];
  const bearPoints = [];

  if (advN > decN) bullPoints.push("\u4e0a\u6da8\u5bb6\u6570\u591a\u4e8e\u4e0b\u8dcc\uff0c\u591a\u5934\u5360\u4f18");
  else if (decN > advN) bearPoints.push("\u4e0b\u8dcc\u5bb6\u6570\u591a\u4e8e\u4e0a\u6da8\uff0c\u7a7a\u5934\u5360\u4f18");

  if (fgValue != null && fgValue >= 60) bullPoints.push(`\u60c5\u7eea\u8bc4\u5206${fgValue}\u5206\uff0c\u5e02\u573a\u504f\u4e50\u89c2`);
  else if (fgValue != null && fgValue < 40) bearPoints.push(`\u60c5\u7eea\u8bc4\u5206${fgValue}\u5206\uff0c\u5e02\u573a\u504f\u60b2\u89c2`);

  if (sentiment?.positive > sentiment?.negative) bullPoints.push("\u6b63\u9762\u65b0\u95fb\u591a\u4e8e\u8d1f\u9762\uff0c\u60c5\u7eea\u504f\u6696");
  else if (sentiment?.negative > sentiment?.positive) bearPoints.push("\u8d1f\u9762\u65b0\u95fb\u591a\u4e8e\u6b63\u9762\uff0c\u60c5\u7eea\u504f\u51b7");

  if ((headlines || []).length > 0) {
    bullPoints.push("\u6709" + headlines.length + "\u6761\u76f8\u5173\u65b0\u95fb\uff0c\u5e02\u573a\u5173\u6ce8\u5ea6\u9ad8");
  }

  const riskLevel = fgValue >= 70 ? "\u4e2d" : fgValue >= 40 ? "\u4f4e" : "\u9ad8";
  const strategyLevel = fgValue >= 60 ? "\u6fc0\u8fdb" : fgValue >= 40 ? "\u7a33\u5065" : "\u4fdd\u5b88";
  const riskColor = riskLevel === "\u9ad8" ? "#fb7185" : riskLevel === "\u4e2d" ? "#f59e0b" : "#34d399";
  const strategyColor = strategyLevel === "\u6fc0\u8fdb" ? "#34d399" : strategyLevel === "\u4fdd\u5b88" ? "#fb7185" : "#818cf8";

  return (
    <div className="space-y-3">
      {/* Market Sentiment Block */}
      <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="text-base font-bold text-slate-200">{"\u5e02\u573a\u60c5\u7eea"}</span>
              <SentimentLabel label={sentiment?.label} />
            </div>
            {fgValue != null && (
              <p className="text-3xl font-extrabold" style={{ color: fgColor }}>{fgLabel}</p>
            )}
            <p className="mt-1 text-base font-medium text-slate-400">
              {scopeLabel}{"("}{totalN}{"\u53EA)\uFF1A"}{"\u4e0a\u6da8"} {advN} {"\u5bb6\u3001\u4e0b\u8dcc"} {decN} {"\u5bb6"}
              {unchN > 0 ? `\u3001\u5e73\u76d8 ${unchN} \u5bb6` : ""}
              {advN > decN ? "\uff0c\u591a\u5934\u5360\u4f18" : decN > advN ? "\uff0c\u7a7a\u5934\u5360\u4f18" : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-right">
            <StatItem label={"\u4e0a\u6da8\u5bb6\u6570"} value={advN} color="#34d399" />
            <StatItem label={"\u4e0b\u8dcc\u5bb6\u6570"} value={decN} color="#fb7185" />
            {unchN > 0 && <StatItem label={"\u5e73\u76d8\u5bb6\u6570"} value={unchN} />}
          </div>
        </div>
        {fgValue != null && (
          <p className="mt-2 text-base font-medium text-slate-400">
            {"\u5e02\u573a\u60c5\u7eea\u8bc4\u5206"}{fgValue}{"\u5206\uff08"}{fgLabel}{"\uff09\uff0c"}
            {fgValue >= 60 ? "\u591a\u5934\u6c14\u6c1b\u6d53\u539a\uff0c\u8d44\u91d1\u505a\u591a\u610f\u613f\u8f83\u5f3a" :
             fgValue >= 40 ? "\u5e02\u573a\u60c5\u7eea\u5e73\u7a33\uff0c\u89c2\u671b\u6c14\u6c1b\u504f\u91cd" :
             "\u6050\u614c\u60c5\u7eea\u8513\u5ef6\uff0c\u8c28\u614e\u4e3a\u4e3b"}{"\u3002"}
          </p>
        )}
      </div>

      {/* Market Analysis Block */}
      <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5 shadow-xl backdrop-blur-md">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-base font-bold text-slate-200">{"\u5e02\u573a\u5206\u6790"}</span>
          <div className="flex gap-2">
            <span className="rounded border border-slate-800/60 px-2.5 py-1 text-sm font-bold"
              style={{ color: strategyColor, background: strategyColor + "18" }}>
              {"\u7b56\u7565\uff1a"}{strategyLevel}
            </span>
            <span className="rounded border border-slate-800/60 px-2.5 py-1 text-sm font-bold"
              style={{ color: riskColor, background: riskColor + "18" }}>
              {"\u98ce\u9669\uff1a"}{riskLevel}
            </span>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-2">
          {bullPoints.map((p, i) => (
            <div key={"b"+i} className="flex items-start gap-2 text-base font-medium text-slate-200">
              <Dot color="#34d399" />
              <span>{p}</span>
            </div>
          ))}
          {bearPoints.map((p, i) => (
            <div key={"r"+i} className="flex items-start gap-2 text-base font-medium text-slate-200">
              <Dot color="#fb7185" />
              <span>{p}</span>
            </div>
          ))}
        </div>

        {/* Headlines */}
        {(headlines || []).length > 0 && (
          <div className="mt-3 space-y-1.5">
            {headlines.slice(0, 3).map((h, i) => (
              <a key={i} href={h.link} target="_blank" rel="noopener noreferrer"
                className="flex items-start gap-2 text-sm font-medium text-slate-400 transition-colors hover:text-indigo-400">
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
            {"\u64cd\u4f5c\u5efa\u8bae"}
          </div>
          <p className="text-base font-medium leading-relaxed text-amber-400/80">
            {fgValue >= 60
              ? "\u5e02\u573a\u60c5\u7eea\u504f\u70ed\uff0c\u53ef\u9002\u5f53\u53c2\u4e0e\u5f3a\u52bf\u6807\u7684\uff0c\u4f46\u6ce8\u610f\u63a7\u5236\u4ed3\u4f4d\uff0c\u9632\u8303\u8ffd\u9ad8\u98ce\u9669\u3002"
              : fgValue >= 40
                ? "\u5e02\u573a\u60c5\u7eea\u4e2d\u6027\uff0c\u5efa\u8bae\u4ee5\u89c2\u671b\u4e3a\u4e3b\uff0c\u7cbe\u9009\u4e2a\u80a1\uff0c\u8f7b\u4ed3\u8bd5\u63a2\u3002"
                : "\u5e02\u573a\u60c5\u7eea\u504f\u51b7\uff0c\u5efa\u8bae\u51cf\u4ed3\u9632\u5b88\uff0c\u7b49\u5f85\u4f01\u7a33\u4fe1\u53f7\u540e\u518d\u5165\u573a\u3002"}
          </p>
        </div>
      </div>
    </div>
  );
}
