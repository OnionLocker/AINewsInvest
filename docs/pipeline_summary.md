# Alpha Vault / AINewsInvest — 完整 Pipeline 摘要

> 面向工程复盘：六层管线一次说清。详细 ASCII 流程图见仓库根目录 [`PIPELINE_FLOW.md`](../PIPELINE_FLOW.md)。

## 1. 入口与触发

| 方式 | 说明 |
|------|------|
| **内置调度** | `pipeline/scheduler.py`，美东 `us_run_time`（默认 07:30 ET）、港股 `hk_run_time`（可空=关闭）；仅 **工作日**。在 `main.py serve` 进程内随服务启动。 |
| **手动 CLI** | `python main.py run --market us_stock [--force]`：跑 **单日、单市场** 完整管线；`--force` 忽略「今日已有推荐」跳过逻辑。 |
| **仅 Layer1 筛股** | `python main.py screen --market us_stock --top-n 40`：量化初筛，**不调用 LLM**。 |

配置：`config.yaml` → `scheduler`、`pipeline`、`llm`、`agent`。

## 2. 六层管线（执行顺序）

| 层 | 模块 / 职责 | 要点 |
|----|----------------|------|
| **Regime** | `runner._check_market_regime` | SPY/指数 + VIX（美股）等；`crisis` 时美股可压 `max_recs`，港股 crisis 可直接空仓。 |
| **Layer 1** | `pipeline/screening.py` → `run_screening` | 股票池硬过滤 → Stage A/B → 趋势/绝对分 → **行业均衡到 `max_candidates`（如 40）**。 |
| **Layer 2** | `build_enriched_candidates` | K 线与技术指标富集，供下游 Agent。 |
| **Layer 3** | `agents` → NewsSkill | 多源新闻 + **LLM 新闻情绪**（批量）；再 **news filter** 收到约 15 只量级（依配置与日志）。 |
| **Layer 4** | TechSkill | 确定性技术分 + 部分标的 **LLM 技术验证**。 |
| **Layer 5** | `synthesize_agent_results` | 新闻/技术矛盾过滤、内幕等惩罚、加权合成、`min_score` / `min_conf`（配置于 `pipeline.synthesis` 等）。 |
| **Layer 6** | `_compute_trade_params` 等 | 入场/止损/止盈、**R:R ≥ 1.5** 否则整票丢弃；写库、发布推荐。 |

核心代码入口：`pipeline/runner.py` → `run_daily_pipeline`。

## 3. 输出与「无推荐」的常见原因

- **合成未过线**：日志常见 `No stocks passed min_score=… & min_conf=… (top: score=…, conf=…). Sit out today.`
- **信号矛盾**：`news=buy` + `tech=avoid` → 跳过。
- **R:R 不达标**：奖励风险比 &lt; 1.5 → 不推荐。
- **Regime / crisis**：极端行情下可能 0 条。
- **非 LLM 失败**：新闻源超时（如 MarketAux）、SEC 500 等，与 `chat_completion` 超时是不同类问题。

## 4. 关键文件速查

| 路径 | 作用 |
|------|------|
| `pipeline/runner.py` | 管线编排、`force`、跳过「今日已跑」 |
| `pipeline/scheduler.py` | 美东/香港本地时钟、工作日 Timer |
| `pipeline/screening.py` | Layer1–2 筛股与富集 |
| `pipeline/agents.py` | Layer3–6 合成与风控 |
| `analysis/llm_client.py` | OpenAI 兼容调用、超时 |
| `config.yaml` | 调度时间、LLM、`pipeline.synthesis` 阈值 |

## 5. 运维日志

- 服务：`logs/serve.log`（调度与管线主日志）。

---

## 附录：2026-04-09 跑批摘要（供对照）

| 事件 | 说明 |
|------|------|
| 调度跑批 | UTC `11:30` 对应美东 07:30 EDT，`us_stock` 跑完全程 → **0 条推荐**（合成门槛 + 矛盾/内幕等）；当日日志含部分 **LLM timeout**。 |
| 手动 `run --force` | 同日后续手动重跑：LLM 批次均 **success**，仍 **0 条推荐**（阈值与过滤逻辑同上）；详见 [`pipeline_digest_2026-04-09.md`](pipeline_digest_2026-04-09.md)。 |
| **v7 部署 + 再跑** | 拉取 `59a3640`、重建前端并重启服务后，`run --force` → **5 条推荐**；问题清单与评审见 [`pipeline_digest_2026-04-09_engineering_review.md`](pipeline_digest_2026-04-09_engineering_review.md)。 |

---

*本文档随仓库版本迭代；业务阈值以 `config.yaml` 与代码为准。*
