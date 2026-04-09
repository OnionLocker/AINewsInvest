# Pipeline 摘要 · 2026-04-09（us_stock）

> 来源：`logs/serve.log` 中当日调度一次完整跑批。供工程侧复盘。  
> **完整六层流程说明**见同目录 [`pipeline_summary.md`](pipeline_summary.md)。  
> **同日 v7 上线后成功发布 5 条推荐 + 问题清单 + 工程评审**见 [`pipeline_digest_2026-04-09_engineering_review.md`](pipeline_digest_2026-04-09_engineering_review.md)。

## 调度与时间

| 项 | 值 |
|----|-----|
| 触发方式 | 内置 scheduler，`trigger_source=scheduler` |
| 市场本地时间 | **07:30 America/New_York（ET）** |
| 日志时间戳（UTC） | `2026-04-09 11:30:00`（与 EDT 07:30 对齐） |
| 港股 | `hk_run_time` 为空，**未调度 hk_stock** |

## 跑批结果

| 项 | 值 |
|----|-----|
| **发布推荐数** | **0** |
| 直接原因 | 合成层未过线：`No stocks passed min_score=58 & min_conf=50 (top: score=29, conf=35). Sit out today.` |
| Scheduler 行 | `us_stock pipeline done, 0 recommendations` |
| 下一档美股 | `2026-04-10 07:30 ET` |

## 市场状态（runner）

- Regime：`normal`
- 摘要：`1d=+2.5% 5d=+3.2% VIX≈21.5`，收益率曲线 spread≈0.371，`macro_risk=low`

## Layer 1 筛股（节选）

- 股票池：`517` symbols（`data/stock_pool.json`）
- Stage A hard filter：`517 → 492`
- Pre-rank → Stage B：`120 → 99`（quality gate）
- Trend / 绝对分等：`99 → 40` 进入后续 Layer 2
- Benchmark 60d return：约 `-2.15%`（日志）

## Layer 3–4（agent 节选）

- NewsSkill：`30` 只候选的新闻批处理完成；Layer 3 news filter：`30 → 15`
- TechSkill：`15` 条里 `6` 条走 LLM verification，其余 deterministic
- 合成阶段：`skipped 6 hold + 5 contradictions`（新闻 buy vs 技术 avoid 等）
- 内幕减持惩罚示例日志：`SBAC`、`ABNB`、`URI`、`EMR`（Heavy insider selling → score 下调）

## 异常与风险点

1. **LLM 超时**：多条 `LLM request failed: timed out` / `news_sentiment_agent` 重试后出现 `LLM returned None`，可能影响该批次打分稳定性。
2. **SEC EDGAR**：`APH`、`NDAQ` 搜索返回 HTTP 500（上游 efts.sec.gov）。
3. **与「无推荐」关系**：日志最终仍明确为 **阈值未过**（最高分 29 < 58），非「管线未启动」。

## 建议工程 agent 关注的代码位置

- 合成门槛：`pipeline/agents.py` → `synthesize_agent_results`（`min_score` / `min_conf`）
- LLM 客户端超时：`analysis/llm_client.py` → `chat_completion`
- 调度：`pipeline/scheduler.py`；配置：`config.yaml` → `scheduler`、`pipeline.synthesis`

---
*文件由运维摘要生成，不含密钥；详细原始日志见部署机 `logs/serve.log`。*
