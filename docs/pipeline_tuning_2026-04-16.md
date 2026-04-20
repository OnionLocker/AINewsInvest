# Pipeline Tuning — 2026-04-16 (v8)

> 本次调优的核心目标：**提高系统胜率、扩大候选池质量、让推荐更符合用户直觉**。

---

## 背景

通过分析 2026-04-16 的管线日志，发现三个结构性问题导致推荐结果偏离预期：

1. 系统从未推荐过 AAPL、NVDA、MSFT、GOOGL、META 等用户最熟悉的蓝筹股
2. 最终输出的 quality tier 几乎全是 low，系统自己对推荐信心不足
3. 28 个候选中有 11 个因 R:R 不足被标为 watch-only，可选范围过窄

---

## 改动 1：换手率分级门槛（P0 — 影响最大）

**文件**: `pipeline/screening.py` — Stage A 硬过滤

### 问题

`min_turnover_ratio = 0.003`（0.3%）要求每日成交金额 ≥ 市值的 0.3%。

美股超大盘股的换手率**天然极低**（因为分母是数万亿市值），导致它们全部被过滤：

| 股票 | 日成交额 | 市值 | 换手率 | 结果 |
|------|---------|------|--------|------|
| NVDA | $71.7B | $4.8T | 0.15% | 被杀 |
| AAPL | $30.9B | $3.9T | 0.08% | 被杀 |
| MSFT | $51.7B | $3.1T | 0.17% | 被杀 |
| META | $15.9B | $1.7T | 0.09% | 被杀 |

这些股票日均成交数十亿美元，流动性完全没问题。0.3% 的门槛源自 A 股经验，对美股大盘股不适用。

### 改法

**分级门槛**，按市值分档：

| 市值区间 | 换手率门槛 | 理由 |
|---------|-----------|------|
| ≥ $500B（mega-cap） | 豁免（0） | dollar_volume 门槛已足够 |
| $50B ~ $500B（large-cap） | 0.1%（原值 ×0.33） | 放松但仍过滤真正的"死水"大盘股 |
| < $50B（mid/small） | 0.3%（不变） | 中小盘仍需换手率保护 |

### 对胜率的预期影响

**正面**。大盘蓝筹股的技术分析信号更可靠（机构行为规律）、bid-ask spread 更小（执行更优）、新闻覆盖更及时（情绪信号更准）。

---

## 改动 2：Insider Selling 惩罚柔化（P1）

**文件**: `pipeline/agents.py` — `_compute_confidence()` 和 `synthesize_agent_results()`

### 问题

原来 `strong_sell` 触发两处惩罚：
- `_compute_confidence()`: confidence -= 15
- `synthesize_agent_results()`: combined_score -= 15

总计 -30 的影响。在 2026-04-16 的日志中，**几乎每一只候选股都被扣了 15 分**。

根本原因：美股上市公司高管普遍通过 **10b5-1 计划**进行常规减持，这是正常的流动性管理，不代表看空。数据源无法区分"计划性减持"和"恐慌性抛售"，导致 `strong_sell` 被大面积误触发。

### 改法

| 位置 | 原值 | 新值 |
|------|------|------|
| `_compute_confidence` → strong_sell | -15 | -8 |
| `_compute_confidence` → moderate_sell | -6 | -4 |
| `synthesize_agent_results` → strong_sell score penalty | -15 | -8 |

Risk flag 文案从"高管大幅减持"改为"高管减持"（语气降级）。

### 对胜率的预期影响

**正面**。避免大量候选因正常减持被过度惩罚，让真正有交易价值的票不会因为噪声数据被压分出局。同时 -8 的惩罚仍然存在，遇到真正的异常抛售信号仍会降权。

### 后续改进方向

如果数据源未来能区分 10b5-1 计划减持 vs 非计划减持，应只对后者施加惩罚。

---

## 改动 3：Short-term R:R 门槛下调（P2）

**文件**: `pipeline/agents.py` — `_compute_trade_params()` 和 `_compute_short_trade_params()`

### 问题

R:R（风险回报比）门槛统一为 1.5，在短线策略下过严：

- 2026-04-16 有 11/28 候选被 R:R 拒绝
- 其中多只 R:R 在 1.2~1.4 之间（如 WDAY=1.41, UAL=1.28），对 1-3 天持仓来说完全可交易
- 过严的门槛导致系统"只能看不能推"

### 改法

| 策略 | 原 R:R 门槛 | 新 R:R 门槛 | 理由 |
|------|------------|------------|------|
| short_term | 1.5 | **1.2** | 短线持仓时间短，1.2 的 R:R 已经合理 |
| swing | 1.5 | 1.5（不变） | 波段持仓时间长，需更严格的奖惩比 |

两处修改：`_compute_trade_params`（多头）和 `_compute_short_trade_params`（空头）。

### 对胜率的预期影响

**中性偏正面**。放宽 R:R 会增加推荐数量，其中部分票可能 R:R 偏低。但结合 conviction_score 排序和 quality_tier 机制，系统仍会优先推出高质量标的。净效果是候选池更丰富，顶部推荐质量不降。

---

## 未改动但需关注的参数

| 参数 | 当前值 | 观察 |
|------|--------|------|
| `quality_threshold` | 55 | 决定是否显示交易参数，暂不调整 |
| `high_min_conviction` | 42.0 | 今天 0 个 high tier，可能需下调到 35-38 |
| `max_daily_change_pct` | 10% | 合理，保持不变 |
| `min_avg_dollar_volume_20d` | $200M | Stage B 精确过滤，保持不变 |

---

## 改动 4：Swing top_n 提升到 5（与 short_term 对齐）

**文件**: `pipeline/config.py` — `SwingConfig`

### 问题

短线 `top_n_normal=5`，但 swing 只有 `top_n_normal=3`。用户期望长线和短线各推 5 只。

### 改法

| 参数 | 原值 | 新值 |
|------|------|------|
| `top_n_normal` | 3 | 5 |
| `top_n_cautious` | 3 | 5 |
| `top_n_bearish` | 2 | 3 |

---

## 改动 5：短线/长线交叉去重（P0 体验问题）

**文件**: `pipeline/agents.py` — 新增 `_cross_dedup_strategies()`

### 问题

v7 的 dual 模式下，`synthesize_agent_results` 分别为短线和长线各跑一遍，然后简单合并。同一只票（如 SHOP、BX）经常同时出现在两个列表中，导致用户看到"5条推荐"实际只有 3 个不同的股票，感觉被凑数。

### 改法

1. `synthesize_agent_results` 新增参数 `_dedup_pool_multiplier`，dual 模式下传入 `2`，让每个策略多返回 2× 候选
2. 新增 `_cross_dedup_strategies(short_recs, swing_recs)` 函数：
   - 检测两个列表中的重复 ticker
   - 按 `conviction_score` 高者保留，低分侧删除该 ticker
   - 低分侧的空位由备选池中的下一个 unique 标的填补
   - 最终各截断到 `top_n`

### 对用户体验的影响

**显著提升**。用户看到短线 5 只 + 长线 5 只 = 10 只不同的股票（极端情况下仍可能有少量重叠，但概率大幅降低）。

---

## 改动 6：LLM JSON 解析鲁棒性提升

**文件**: `analysis/llm_client.py` — `_extract_json()` 和 `agent_analyze()`

### 问题

2026-04-16 的管线运行中有 **33 次 JSON 解析失败**。LLM（尤其是中文模型）经常在 JSON 前面加一段自然语言分析，例如：

> 基于你给的这 10 只候选，我会先按"短线延续性 + 风险回报 + 位置不过热"来筛...

原有的 `_extract_json` 用 `text.find("{")` / `text.rfind("}")` 做简单匹配，但遇到多层嵌套、引号内的花括号、或不完整 JSON 时会失败。

### 改法

**解析端（`_extract_json`）**：
- 替换为完整的 **括号计数解析器**（brace-counting parser），正确处理字符串内的转义字符和嵌套结构
- 优先级：markdown fence → 全文 JSON → 括号计数提取

**Prompt 端（`agent_analyze`）**：
- 在 user message 末尾追加 JSON 格式强制提示
- 重试时将上一次错误输出作为 context，追加更强的纠正指令（"Your previous response was NOT valid JSON..."），引导 LLM 在第 2/3 次尝试时直接输出纯 JSON

### 预期效果

- 解析成功率从约 60-70%（33/~100 失败）提升到 90%+
- 重试次数减少（第 2 次尝试有纠正 context，成功率更高）
- 最终 fallback 仍然存在（deterministic scoring），系统不会因 LLM 失败而无输出

---

## 未改动但需关注的参数

| 参数 | 当前值 | 观察 |
|------|--------|------|
| `quality_threshold` | 55 | 决定是否显示交易参数，暂不调整 |
| `high_min_conviction` | 42.0 | v8 后 high tier 已有 3 个，暂不调整 |
| `max_daily_change_pct` | 10% | 合理，保持不变 |
| `min_avg_dollar_volume_20d` | $200M | Stage B 精确过滤，保持不变 |
| MarketAux 免费版 | 几乎无数据返回 | 免费版限制较紧，但 Finnhub + Yahoo + Google + SEC 四源已足够 |

---

## 版本标记

本次改动在代码注释中标记为 **v8**，与之前的 v3.x / v6 / v7 区分。

## 改动文件清单

| 文件 | 改动点 |
|------|--------|
| `pipeline/screening.py` | 换手率分级门槛（改动 1） |
| `pipeline/agents.py` | Insider 惩罚柔化（改动 2）、R:R 门槛下调（改动 3）、交叉去重（改动 5） |
| `pipeline/config.py` | Swing top_n 提升（改动 4） |
| `analysis/llm_client.py` | JSON 解析增强 + prompt 优化（改动 6） |
| `docs/pipeline_tuning_2026-04-16.md` | 本文档 |
