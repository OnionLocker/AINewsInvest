# Pipeline 摘要 · 2026-04-15（us_stock）— 工程微调用

> 来源：部署机 `logs/serve.log` 当日 **调度器触发** 的完整跑批。  
> 提交基线：`653f393`（`feat: 工程质量加固 + 流动性筛选修复 + 技术旁路安全性`）。

## 调度与时间

| 项 | 值 |
|----|-----|
| 触发 | `scheduler` → `us_stock` |
| 日志 UTC 起 | `2026-04-15 11:30:00`（≈ **美东 07:30 EDT**；≈ **北京时间 19:30**） |
| 调度结束 | `2026-04-15 11:55:24.805 | Scheduler: us_stock pipeline done, 5 recommendations` |
| 粗算耗时 | ~**25 分钟**（11:30 → 11:55 UTC） |
| 下一档 | `Next us_stock pipeline: 2026-04-16 07:30 ET` |

## 跑批结果

| 项 | 值 |
|----|-----|
| **发布推荐** | **5**（`Published 5 recommendations (20260415, us_stock)`） |
| `ref_date` | `20260415` |
| Layer 1 出口 | `129 -> 60 candidates`（日志含 **20d 流动性**筛选、行业上限等） |
| NewsSkill | **6 批 × 10 = 60** 只（`batch 1/6` … `6/6`） |
| 合成（节选） | `Synthesis notes: 48 hold + 6 contradictions + 20~24 R:R insufficient`；`Quality tier distribution: {'high': 3, 'medium': 16, 'low': 28}` |
| 相关性过滤 | `47 -> 20 items` 后进入发布前 |
| 盘前胜率评估 | `Pre-run evaluation` 含 `partial_win` / `still_pending` 等；`evaluate_pending_records` 亦有 1 条结算 |

## 市场缓存（管线尾部）

- `Market sentiment cached for us_stock: fg=40.0, breadth=501`（标普宽度成分已能拉取时 breadth 非 0）。

## 异常与风险点（建议微调）

1. **LLM**  
   - `LLM network error ... timed out`（重试后继续）。  
   - `JSON parse failed`：`technical_agent` / `news_sentiment_agent` 首轮返回非 JSON 或夹杂说明文字（重试后多批成功）。  
   - 一条：`technical_agent` 出现 `raw[:200]=No response from OpenClaw.` —— 与 **OpenClaw gateway** 可用性/超时相关。

2. **SEC EDGAR**  
   - 部分 ticker（如 `NDAQ`、`PEP`、`UAL`）`efts.sec.gov` **HTTP 500**。

3. **行情符号**  
   - `^HSTECH`、`BRK.B`、`BF.B` 等 Yahoo 侧 **404 / 无数据** 或 `get_quote` 报错（港股/特殊代码格式）。

4. **R:R / 内幕**  
   - 大量 `R:R insufficient` → `watch-only`；多 `Heavy insider selling` 扣分。

## 建议工程师关注的代码位置

- `analysis/llm_client.py`：超时、JSON 解析、重试策略  
- `pipeline/agents.py`：`synthesize_agent_results`、R:R 与相关性过滤  
- `pipeline/skills/*`：Tech/News 输出格式约束（减少 JSON parse failed）  
- OpenClaw：`127.0.0.1:18789` 稳定性与超时

---
*不含密钥；细节以服务器 `logs/serve.log` 为准。*
