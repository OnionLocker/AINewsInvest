import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import {
  Activity,
  TrendingUp,
  TrendingDown,
  Cpu,
  ChevronRight,
  BarChart2,
  AlertCircle,
  RefreshCw,
  DollarSign,
  Globe,
} from "lucide-react";

function SentimentLabel({ value }) {
  if (value >= 75) return { text: "鏋佸害璐┆", color: "rose" };
  if (value >= 60) return { text: "鍋忕儹", color: "rose" };
  if (value >= 40) return { text: "涓€�", color: "slate" };
  if (value >= 25) return { text: "鍋忓喎", color: "emerald" };
  return { text: "鏋佸害鎭愭儳", color: "emerald" };
}

function WinRateLabel(rate) {
  if (rate >= 60) return "琛ㄧ幇浼樼";
  if (rate >= 50) return "璺戣耽澶х洏";
  if (rate >= 40) return "琛ㄧ幇涓€鑸�";
  return "寰呮敼鍠�";
}

function ActionLabel(item) {
  const score = item.combined_score ?? item.score ?? 0;
  const dir = item.direction;
  if (dir === "short") return "鍋氱┖";
  if (score >= 75) return "绉瀬涔板叆";
  if (score >= 60) return "寤鸿涔板叆";
  if (score >= 45) return "瑙傛湜";
  return "涓嶅缓璁粙鍏�";
}

function ActionBadgeColor(label) {
  if (label === "绉瀬涔板叆" || label === "寤鸿涔板叆")
    return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.1)]";
  if (label === "瑙傛湜")
    return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  if (label === "鍋氱┖")
    return "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20";
  return "bg-slate-800 text-slate-400 border-slate-700";
}

function SkeletonBlock({ className = "" }) {
  return <div className={`bg-slate-800/50 animate-pulse rounded-lg ${className}`} />;
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [market, setMarket] = useState("us");
  const [sentiment, setSentiment] = useState(null);
  const [winRate, setWinRate] = useState(null);
  const [recs, setRecs] = useState(null);
  const [indices, setIndices] = useState([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [sentRes, wrRes, recRes, idxRes] = await Promise.allSettled([
        api.marketSentiment(market),
        api.winRateSummary(),
        api.marketTodayRecs(market),
        api.marketOverview(),
      ]);
      if (sentRes.status === "fulfilled") setSentiment(sentRes.value);
      if (wrRes.status === "fulfilled") setWinRate(wrRes.value);
      if (recRes.status === "fulfilled") setRecs(recRes.value);
      if (idxRes.status === "fulfilled") setIndices(idxRes.value || []);
    } catch (e) {
      console.error("Dashboard fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, [market]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const mktKey = market === "us" ? "us_stock" : "hk_stock";
  const fg = sentiment?.fear_greed ?? { value: 0, label: "鏈煡" };
  const sentInfo = SentimentLabel({ value: fg.value });

  const wr = winRate?.[mktKey]?.["30d"] ?? winRate?.overall ?? {};
  const wrValue = wr.win_rate ?? 0;
  const wrLabel = WinRateLabel(wrValue);
  const wrTotal = wr.total_evaluated ?? 0;
  const wrPending = wr.pending ?? 0;

  const items = recs?.items ?? [];
  const displayMsg = recs?.display_message;
  const todayDate = new Date().toISOString().split("T")[0];

  const marketIndices = indices.filter(
    (idx) => idx.market === mktKey,
  );

  return (
    <div className="min-h-screen text-slate-200 font-sans selection:bg-indigo-500/30">
      {/* Header */}
      <header className="mb-8 flex flex-col md:flex-row justify-between md:items-end border-b border-slate-800/60 pb-6">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-white mb-1">
            Alpha<span className="font-semibold text-indigo-400">Vault</span>
          </h1>
          <p className="text-slate-400 text-sm flex items-center gap-2">
            <Activity className="w-4 h-4" /> AI 鎶曠爺涓庢儏缁垎鏋愮郴缁�
          </p>
        </div>
        <div className="mt-4 md:mt-0 flex items-center gap-4">
          {/* Market Toggle */}
          <div className="flex rounded-lg border border-slate-800 overflow-hidden">
            <button
              onClick={() => setMarket("us")}
              className={`px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 transition-colors ${
                market === "us"
                  ? "bg-indigo-500/15 text-indigo-400 border-r border-slate-800"
                  : "text-slate-500 hover:text-slate-300 border-r border-slate-800"
              }`}
            >
              <DollarSign className="w-3 h-3" /> 缇庤偂
            </button>
            <button
              onClick={() => setMarket("hk")}
              className={`px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 transition-colors ${
                market === "hk"
                  ? "bg-amber-500/15 text-amber-400"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              <Globe className="w-3 h-3" /> 娓偂
            </button>
          </div>
          <button
            onClick={fetchData}
            className="p-2 text-slate-400 hover:text-indigo-400 hover:bg-slate-900 rounded-full transition-colors"
            title="鍒锋柊鏁版嵁"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? "animate-spin" : ""}`} />
          </button>
          <div>
            <p className="text-slate-500 text-xs uppercase tracking-widest mb-1">褰撳墠浜ゆ槗鏃�</p>
            <p className="text-xl font-medium text-slate-200">
              {loading ? <SkeletonBlock className="h-6 w-24" /> : todayDate}
            </p>
          </div>
        </div>
      </header>

      {/* Market Indices Bar */}
      {marketIndices.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
          {marketIndices.map((idx, i) => (
            <div key={i} className="bg-slate-900/40 border border-slate-800/60 rounded-xl px-4 py-3">
              <p className="text-slate-400 text-xs mb-1">{idx.name}</p>
              <div className="flex items-baseline justify-between">
                <span className="text-white font-medium text-sm tabular-nums">
                  {idx.price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "--"}
                </span>
                <span className={`text-xs font-medium tabular-nums ${
                  (idx.change_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}>
                  {(idx.change_pct ?? 0) >= 0 ? "+" : ""}{idx.change_pct?.toFixed(2) ?? "0.00"}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        {/* Card 1: Market Sentiment */}
        <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6 shadow-xl relative overflow-hidden group hover:border-slate-700/80 transition-colors">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Activity className="w-16 h-16 text-rose-400" />
          </div>
          <h3 className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-3">
            {market === "us" ? "缇庤偂" : "娓偂"}甯傚満鎯呯华娓╁害
          </h3>
          {loading ? (
            <SkeletonBlock className="h-12 w-1/2 mb-4" />
          ) : (
            <>
              <div className="flex items-baseline gap-3">
                <span className={`text-5xl font-light ${
                  sentInfo.color === "rose" ? "text-rose-400"
                    : sentInfo.color === "emerald" ? "text-emerald-400"
                    : "text-slate-300"
                }`}>
                  {Math.round(fg.value)}掳
                </span>
                <span className={`text-xs px-2.5 py-1 rounded-md border font-medium ${
                  sentInfo.color === "rose"
                    ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                    : sentInfo.color === "emerald"
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : "bg-slate-800 text-slate-300 border-slate-700"
                }`}>
                  {fg.label}
                </span>
              </div>
              {sentiment?.breadth && sentiment.breadth.total > 0 && (
                <p className="text-slate-500 text-xs mt-4 flex items-center gap-1">
                  {sentiment.breadth.advance_pct >= 50 ? (
                    <><TrendingUp className="w-3 h-3 text-emerald-400" /> 涓婃定鍗犳瘮 {sentiment.breadth.advance_pct}%</>
                  ) : (
                    <><TrendingDown className="w-3 h-3 text-rose-400" /> 涓婃定鍗犳瘮 {sentiment.breadth.advance_pct}%</>
                  )}
                  <span className="text-slate-600 ml-1">({sentiment.breadth_scope})</span>
                </p>
              )}
              {sentiment?.headlines?.length > 0 && (
                <div className="mt-3 space-y-1">
                  {sentiment.headlines.slice(0, 2).map((h, i) => (
                    <a key={i} href={h.link} target="_blank" rel="noreferrer"
                       className="block text-xs text-slate-500 hover:text-slate-300 truncate transition-colors">
                      鈥� {h.title}
                    </a>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Card 2: Win Rate */}
        <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6 shadow-xl relative overflow-hidden group hover:border-slate-700/80 transition-colors">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <BarChart2 className="w-16 h-16 text-emerald-400" />
          </div>
          <h3 className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-3">杩�30鏃ユ帹鑽愯儨鐜�</h3>
          {loading ? (
            <SkeletonBlock className="h-12 w-1/2 mb-4" />
          ) : (
            <>
              <div className="flex items-baseline gap-3">
                <span className={`text-5xl font-light ${
                  wrValue >= 50 ? "text-emerald-400" : "text-amber-400"
                }`}>
                  {wrValue}%
                </span>
                <span className={`text-xs px-2.5 py-1 rounded-md border font-medium ${
                  wrValue >= 50
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                }`}>
                  {wrLabel}
                </span>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                <div>
                  <p className="text-emerald-400 text-sm font-medium">{wr.wins ?? 0}</p>
                  <p className="text-slate-600 text-[10px]">鐩堝埄</p>
                </div>
                <div>
                  <p className="text-rose-400 text-sm font-medium">{wr.losses ?? 0}</p>
                  <p className="text-slate-600 text-[10px]">浜忔崯</p>
                </div>
                <div>
                  <p className="text-slate-400 text-sm font-medium">{wr.timeouts ?? 0}</p>
                  <p className="text-slate-600 text-[10px]">瓒呮椂</p>
                </div>
              </div>
              <p className="text-slate-600 text-[10px] mt-2">
                宸茶瘎浼� {wrTotal} 鏉� 路 寰呰瘎浼� {wrPending} 鏉� 路 骞冲潎鏀剁泭 {wr.avg_return_pct?.toFixed(2) ?? "0"}%
              </p>
            </>
          )}
        </div>

        {/* Card 3: System Status */}
        <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6 shadow-xl relative overflow-hidden group hover:border-slate-700/80 transition-colors">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Cpu className="w-16 h-16 text-indigo-400" />
          </div>
          <h3 className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-4">鍙� Agent 鐘舵€�</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center border-b border-slate-800/50 pb-2">
              <span className="text-slate-300 text-sm">鏂伴椈鎯呯华鍒嗘瀽</span>
              <span className="flex items-center gap-2 text-xs font-medium px-2 py-0.5 rounded bg-emerald-400/10 text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                杩愯涓�
              </span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800/50 pb-2">
              <span className="text-slate-300 text-sm">鎶€鏈舰鎬侀噺鍖�</span>
              <span className="flex items-center gap-2 text-xs font-medium px-2 py-0.5 rounded bg-emerald-400/10 text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                杩愯涓�
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-300 text-sm">瀹氭椂璋冨害鍣�</span>
              <span className="flex items-center gap-2 text-xs font-medium px-2 py-0.5 rounded bg-emerald-400/10 text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                杩愯涓�
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Recommendations Table */}
      <section className="bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-2xl p-1 shadow-2xl">
        <div className="bg-slate-950/50 rounded-xl p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-medium text-white flex items-center gap-2">
              浠婃棩绮鹃€夋爣鐨�
              {displayMsg && (
                <span className="text-xs text-amber-400 font-normal ml-2">{displayMsg}</span>
              )}
            </h2>
            <Link
              to={`/recommendations/${market}`}
              className="text-sm font-medium text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors bg-indigo-400/10 hover:bg-indigo-400/20 px-3 py-1.5 rounded-lg"
            >
              鏌ョ湅瀹屾暣鎶ュ憡 <ChevronRight className="w-4 h-4" />
            </Link>
          </div>

          {/* Table Header */}
          <div className="grid grid-cols-6 gap-4 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 px-4 pb-3 border-b border-slate-800/60 hidden md:grid">
            <div className="col-span-1">鏍囩殑</div>
            <div className="col-span-1 text-right">AI缁煎悎璇勫垎</div>
            <div className="col-span-1 text-right">绛栫暐鍏ュ満鍖�</div>
            <div className="col-span-1 text-right">缁撴瀯姝㈡崯</div>
            <div className="col-span-1 text-right">鐩爣姝㈢泩</div>
            <div className="col-span-1 text-right">鎵ц寤鸿</div>
          </div>

          <div className="space-y-2">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="grid grid-cols-1 md:grid-cols-6 gap-4 items-center bg-slate-900/30 rounded-xl p-4 border border-slate-800/30 animate-pulse">
                  <SkeletonBlock className="h-10 w-24" />
                  <SkeletonBlock className="h-8 w-12 justify-self-end" />
                  <SkeletonBlock className="h-6 w-20 justify-self-end" />
                  <SkeletonBlock className="h-6 w-16 justify-self-end" />
                  <SkeletonBlock className="h-6 w-16 justify-self-end" />
                  <SkeletonBlock className="h-8 w-20 justify-self-end" />
                </div>
              ))
            ) : items.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                <AlertCircle className="w-12 h-12 text-slate-700 mb-3" />
                <p>浠婃棩鏆傛棤绗﹀悎绯荤粺椋庢帶鏍囧噯鐨勬帹鑽愭爣鐨�</p>
                <p className="text-sm text-slate-600 mt-1">鑰愬績绛夊緟甯傚満鏈轰細</p>
              </div>
            ) : (
              items.slice(0, 8).map((item, i) => {
                const score = item.combined_score ?? item.score ?? 0;
                const action = ActionLabel(item);
                const entry = item.entry_price
                  ? `${item.entry_price.toFixed(2)}${item.entry_2 ? " - " + item.entry_2.toFixed(2) : ""}`
                  : "--";
                const sl = item.stop_loss ? item.stop_loss.toFixed(2) : "--";
                const tp = item.take_profit ? item.take_profit.toFixed(2) : "--";

                return (
                  <Link
                    key={i}
                    to={`/analysis?ticker=${item.ticker}&market=${item.market}`}
                    className="grid grid-cols-2 md:grid-cols-6 gap-4 items-center bg-slate-900/50 hover:bg-slate-800/80 transition-all duration-200 rounded-xl p-4 border border-transparent hover:border-slate-700/50 cursor-pointer"
                  >
                    <div className="col-span-2 md:col-span-1">
                      <p className="text-slate-200 font-medium text-base mb-0.5">{item.name}</p>
                      <p className="text-slate-500 font-mono text-xs">{item.ticker}</p>
                    </div>

                    <div className="col-span-1 text-left md:text-right flex items-center md:justify-end gap-2">
                      <span className="md:hidden text-xs text-slate-500">璇勫垎:</span>
                      <span className={`text-lg font-semibold ${
                        score >= 75 ? "text-indigo-400" : score >= 60 ? "text-emerald-400" : score >= 45 ? "text-slate-300" : "text-slate-500"
                      }`}>
                        {Math.round(score)}
                      </span>
                    </div>

                    <div className="col-span-1 text-right font-mono text-sm text-slate-300">
                      <span className="md:hidden text-xs text-slate-500 block">鍏ュ満:</span>
                      {entry}
                    </div>

                    <div className="col-span-1 text-right font-mono text-sm text-rose-400/80">
                      <span className="md:hidden text-xs text-slate-500 block">姝㈡崯:</span>
                      {sl}
                    </div>

                    <div className="col-span-1 text-right font-mono text-sm text-emerald-400/80">
                      <span className="md:hidden text-xs text-slate-500 block">姝㈢泩:</span>
                      {tp}
                    </div>

                    <div className="col-span-2 md:col-span-1 flex justify-end mt-2 md:mt-0">
                      <span className={`text-xs px-3 py-1.5 rounded-md font-medium border ${ActionBadgeColor(action)}`}>
                        {action}
                      </span>
                    </div>
                  </Link>
                );
              })
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
