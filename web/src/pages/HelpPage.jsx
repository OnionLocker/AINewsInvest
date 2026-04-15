import { useState } from "react";
import { BookOpen, ChevronDown, ChevronRight, Target, Shield, BarChart3, TrendingUp, AlertTriangle, HelpCircle } from "lucide-react";

const sections = [
  {
    id: "how-it-works",
    icon: Target,
    title: "系统如何工作",
    content: `Alpha Vault 采用 6 层智能分析流水线，每日自动筛选并评估股票：

**第 1 层：量化初筛** — 从 S&P 500 / 恒生指数等成分股中，基于市值、成交量、估值等硬性指标筛选出约 40 只候选股。

**第 2 层：技术数据增强** — 为每只候选股计算 20+ 技术指标（均线、RSI、MACD、布林带、ATR 等），并标注关键信号（金叉、放量突破、超买偏离等）。

**第 3 层：新闻情绪分析** — 从 5 个数据源获取财经新闻，AI 提取催化剂和风险因子，结合确定性评分函数给出新闻评分。技术面强势的个股即使新闻一般也可通过"技术旁路"进入下一层。

**第 4 层：技术面深度分析** — 60% 基于代码计算的硬指标，40% 由 AI 识别的形态和趋势。两者融合产生技术评分。

**第 5 层：综合评分与筛选** — 加权合并新闻、技术、基本面评分。计算置信度（多维度信号一致性）。剔除矛盾信号和低置信度标的。

**第 6 层：风险控制** — 基于 ATR 动态计算入场价、止损、止盈。强制执行最低 1.5:1 风险回报比。根据波动率和市况调整仓位建议。`,
  },
  {
    id: "reading-recommendations",
    icon: BarChart3,
    title: "如何解读推荐",
    content: `每条推荐包含以下关键信息：

**综合评分 (Combined Score)** — 0-100 分，越高越看好。由新闻评分、技术评分、基本面评分加权计算。
- 75+ 分：强烈看好
- 60-75 分：看好
- 55-60 分：谨慎看好（刚过阈值）

**置信度 (Confidence)** — 表示各维度信号的一致程度。
- 80%+：新闻、技术、基本面高度一致
- 60-80%：大致一致，部分信号中性
- 50-60%：信号有分歧，建议轻仓

**方向 (Direction)**
- Buy：做多（大多数推荐）
- Short：做空（仅美股，需要信号强烈一致看空）

**入场价 (Entry)** — 建议限价单入场价。突破型给出接近现价的入场价，回调型给出低于现价的入场价。
- 入场 2 (Entry 2)：分批建仓的第二档入场价

**止损 (Stop Loss)** — 基于 ATR 计算的止损位。实际止损幅度通常在 1.5%-6% 之间。

**止盈目标**
- TP1：第一目标位，基于 ATR 或阻力位
- TP2：第二目标位，可在 TP1 获利后上移止损继续持有
- TP3：最大目标位

**仓位建议 (Position %)** — 建议占总资金的百分比（2%-10%）。高评分 + 高置信度 + 低波动 = 较高仓位。

**风险标记** — 红色标签提示特定风险：超买偏离、量价背离、日周趋势矛盾、高波动、临近财报等。`,
  },
  {
    id: "strategies",
    icon: TrendingUp,
    title: "策略说明",
    content: `系统支持两种交易策略：

**短线策略 (Short-term)**
- 持仓周期：3-5 天
- 权重分配：技术 55% / 新闻 40% / 基本面 5%
- 止损：ATR 2.0 倍（约 2-4%）
- 止盈：ATR 3.0 倍
- 适合：趋势明确的短期波段

**波段策略 (Swing)**
- 持仓周期：10-30 天
- 权重分配：新闻 40% / 技术 35% / 基本面 25%
- 止损：ATR 2.0 倍（允许更大回撤）
- 止盈：ATR 3.5 倍
- 适合：中期趋势和价值回归

**市场状态自适应**
系统会检测当前市场状态并自动调整：
- 正常：标准筛选和推荐
- 谨慎：提高评分阈值，减少推荐数量
- 熊市：大幅提高阈值，仅推荐最强信号
- 危机（VIX > 35 或单日跌 > 3%）：暂停推荐，建议空仓观望`,
  },
  {
    id: "risk-management",
    icon: Shield,
    title: "风险管理",
    content: `**仓位控制**
- 单只个股最大仓位 10%，最小 2%
- 同一行业不超过推荐总数的 40%
- 高相关性个股（>0.7）自动去重

**止损纪律**
- 所有推荐都附带止损位
- 建议使用限价单入场 + 止损单保护
- 追踪止损：盈利达到一定幅度后自动上移止损

**重要提醒**
- 系统推荐仅供参考，不构成投资建议
- 过去的胜率不代表未来的表现
- 请根据自身风险承受能力调整仓位
- 永远不要把全部资金投入单一标的`,
  },
  {
    id: "win-rate",
    icon: Target,
    title: "胜率统计说明",
    content: `**胜率计算方法**
- 胜利：在持仓期内触及 TP1（第一止盈目标）
- 失败：在持仓期内触及止损，或到期时亏损
- 持平：到期时小幅盈亏（<0.5%）

**统计维度**
- 按市场：美股 / 港股分开统计
- 按策略：短线 / 波段分开统计
- 按时间：最近 7 天 / 30 天 / 全部

**评估周期**
- 短线推荐：5 天后评估
- 波段推荐：21 天后评估（保留 90 天）
- 系统每日自动评估到期推荐`,
  },
  {
    id: "faq",
    icon: HelpCircle,
    title: "常见问题",
    content: `**Q: 为什么今天没有推荐？**
A: 这是正常现象。当市场处于危机状态（VIX 飙升、大跌）或没有股票通过置信度阈值时，系统会选择"空仓观望"。这是风控机制在保护你的资金。

**Q: 入场价和现价差很多，还能买吗？**
A: 推荐的入场价是建议的限价单价格。如果现价已远高于入场价，说明已经错过最佳入场点，不建议追高。

**Q: 推荐中的止损幅度太大/太小怎么办？**
A: 止损是基于 ATR（平均真实波幅）计算的，反映了该股票的实际波动特征。你可以根据自身风险偏好微调，但建议不要设得比系统给出的更紧（容易被震出）。

**Q: 新闻评分为什么有时候是 50 分？**
A: 50 分是中性基准分。当 Finnhub/MarketAux API 未配置或新闻数据不足时，系统会给出中性评分，并自动降低新闻在综合评分中的权重。

**Q: 数据多久更新一次？**
A: 系统每日定时运行流水线（默认美东 7:30，开盘前 2 小时）。市场数据（价格、指数）在页面加载时实时获取。

**Q: 可以同时持有多只推荐股票吗？**
A: 可以，但注意总仓位和行业集中度。系统已通过相关性过滤减少了同质化推荐。建议总持仓不超过资金的 50-60%。`,
  },
];

function Section({ section, isOpen, onToggle }) {
  const Icon = section.icon;
  return (
    <div className="rounded-2xl border border-border bg-white shadow-sm">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-surface-3"
      >
        <Icon size={18} className="shrink-0 text-brand" />
        <span className="flex-1 text-[15px] font-semibold text-primary">{section.title}</span>
        {isOpen ? <ChevronDown size={16} className="text-secondary" /> : <ChevronRight size={16} className="text-secondary" />}
      </button>
      {isOpen && (
        <div className="border-t border-border px-5 py-4">
          <div className="prose prose-sm max-w-none text-secondary leading-relaxed whitespace-pre-line">
            {section.content.split("\n").map((line, i) => {
              if (line.startsWith("**") && line.endsWith("**")) {
                return <p key={i} className="mt-3 mb-1 font-semibold text-primary">{line.replace(/\*\*/g, "")}</p>;
              }
              if (line.startsWith("**")) {
                const parts = line.split("**");
                return (
                  <p key={i} className="mt-2">
                    {parts.map((part, j) =>
                      j % 2 === 1 ? <strong key={j} className="text-primary">{part}</strong> : part
                    )}
                  </p>
                );
              }
              if (line.startsWith("- ")) {
                return <p key={i} className="ml-4 mt-0.5">{'\u00B7'} {line.slice(2)}</p>;
              }
              if (line.trim() === "") return <br key={i} />;
              return <p key={i} className="mt-1">{line}</p>;
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function HelpPage() {
  const [openSections, setOpenSections] = useState(new Set(["how-it-works"]));

  const toggle = (id) => {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center gap-3">
        <BookOpen size={24} className="text-brand" />
        <h1 className="text-3xl font-light text-primary">使用指南</h1>
      </div>
      <p className="text-sm text-secondary">
        了解 Alpha Vault 的工作原理、如何解读推荐、以及策略参数说明
      </p>
      <div className="space-y-2">
        {sections.map((s) => (
          <Section
            key={s.id}
            section={s}
            isOpen={openSections.has(s.id)}
            onToggle={() => toggle(s.id)}
          />
        ))}
      </div>
    </div>
  );
}
