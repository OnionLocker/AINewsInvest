import { useState, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api";
import Card, { CardTitle } from "../components/Card";
import Spinner from "../components/Spinner";
import Badge from "../components/Badge";
import { BarChart3, Send, Zap, Shield, TrendingUp, Newspaper } from "lucide-react";

function Section({ title, icon: Icon, children }) {
  return (
    <Card>
      <CardTitle>
        {Icon && <Icon size={14} className="mr-1 inline" />}
        {title}
      </CardTitle>
      {children}
    </Card>
  );
}

export default function AnalysisPage() {
  const [params] = useSearchParams();
  const [ticker, setTicker] = useState(params.get("ticker") || "");
  const [market, setMarket] = useState(params.get("market") || "us_stock");
  const [result, setResult] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [steps, setSteps] = useState([]);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (params.get("ticker") && params.get("market")) {
      handleAnalyze(params.get("ticker"), params.get("market"));
    }
  }, []);

  async function handleAnalyze(t, m) {
    const tk = t || ticker;
    const mk = m || market;
    if (!tk) return;
    setStreaming(true);
    setResult(null);
    setSteps([]);

    try {
      const res = await api.deepAnalysisStream({
        ticker: tk.toUpperCase(),
        market: mk,
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.done) {
              setResult(evt.result);
            } else {
              setSteps((prev) => [...prev, evt]);
            }
          } catch {}
        }
      }
    } catch (err) {
      setSteps((prev) => [
        ...prev,
        { step: "error", message: err.message },
      ]);
    } finally {
      setStreaming(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    handleAnalyze();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">深度分析</h1>

      <Card>
        <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-4">
          <div>
            <label className="mb-1 block text-xs text-gray-400">股票代码</label>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="AAPL"
              className="w-32 rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm uppercase outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-gray-400">市场</label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value)}
              className="rounded-lg border border-surface-3 bg-surface-2 px-3 py-2 text-sm"
            >
              <option value="us_stock">美股</option>
              <option value="hk_stock">港股</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={streaming || !ticker}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {streaming ? <Spinner size="sm" /> : <Send size={16} />}
            {streaming ? "分析中..." : "开始分析"}
          </button>
        </form>
      </Card>

      {steps.length > 0 && !result && (
        <Card>
          <CardTitle>分析进度</CardTitle>
          <div className="space-y-2" ref={scrollRef}>
            {steps.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                {s.step === "error" ? (
                  <span className="text-red-400">{s.message}</span>
                ) : (
                  <>
                    <Zap size={12} className="text-brand-400" />
                    <span className="text-gray-400">
                      {s.step}: {s.message || "完成"}
                    </span>
                  </>
                )}
              </div>
            ))}
            {streaming && <Spinner size="sm" className="mt-2" />}
          </div>
        </Card>
      )}

      {result && (
        <div className="grid gap-4 lg:grid-cols-2">
          {result.technical && (
            <Section title="技术分析" icon={TrendingUp}>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                {Object.entries(result.technical).map(([k, v]) => {
                  if (typeof v === "object" && v !== null) return null;
                  return (
                    <div key={k} className="flex justify-between">
                      <span className="text-gray-500">{k}</span>
                      <span className="text-gray-300">
                        {typeof v === "number" ? v.toFixed(2) : String(v)}
                      </span>
                    </div>
                  );
                })}
              </div>
              {result.technical.signal && (
                <div className="mt-3">
                  <Badge
                    variant={result.technical.signal === "buy" ? "green" : "red"}
                  >
                    信号: {result.technical.signal}
                  </Badge>
                </div>
              )}
            </Section>
          )}

          {result.fundamental && (
            <Section title="基本面分析" icon={Shield}>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                {Object.entries(result.fundamental).map(([k, v]) => {
                  if (typeof v === "object" && v !== null) return null;
                  return (
                    <div key={k} className="flex justify-between">
                      <span className="text-gray-500">{k}</span>
                      <span className="text-gray-300">
                        {typeof v === "number" ? v.toFixed(2) : String(v)}
                      </span>
                    </div>
                  );
                })}
              </div>
              {result.fundamental.risk_flags?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {result.fundamental.risk_flags.map((f, i) => (
                    <Badge key={i} variant="red">{f}</Badge>
                  ))}
                </div>
              )}
            </Section>
          )}

          {result.valuation && (
            <Section title="估值分析" icon={BarChart3}>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                {Object.entries(result.valuation).map(([k, v]) => {
                  if (typeof v === "object" && v !== null) return null;
                  return (
                    <div key={k} className="flex justify-between">
                      <span className="text-gray-500">{k}</span>
                      <span className="text-gray-300">
                        {typeof v === "number" ? v.toFixed(2) : String(v)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </Section>
          )}

          {result.news && (
            <Section title="新闻情绪" icon={Newspaper}>
              {result.news.sentiment && (
                <p className="mb-2 text-xs">
                  情绪:{" "}
                  <Badge
                    variant={
                      result.news.sentiment === "positive"
                        ? "green"
                        : result.news.sentiment === "negative"
                          ? "red"
                          : "gray"
                    }
                  >
                    {result.news.sentiment}
                  </Badge>
                </p>
              )}
              <div className="space-y-2">
                {(result.news.items || []).slice(0, 5).map((n, i) => (
                  <div key={i} className="text-xs text-gray-400">
                    {n.link ? (
                      <a href={n.link} target="_blank" rel="noopener noreferrer"
                        className="font-medium text-brand-400 hover:underline">
                        {n.title}
                      </a>
                    ) : (
                      <p className="font-medium text-gray-300">{n.title}</p>
                    )}
                    <p className="text-gray-600">{n.published} | {n.source}</p>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {result.llm_analysis && (
            <Card className="lg:col-span-2">
              <CardTitle>
                <Zap size={14} className="mr-1 inline" /> AI 分析
              </CardTitle>
              <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap text-xs text-gray-300">
                {result.llm_analysis}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
