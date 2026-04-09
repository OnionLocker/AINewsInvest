# Pipeline 跑批摘要 · 工程评审 · 2026-04-09（us_stock）

> 供工程师 agent 整体评估：含 **同一日** 多次跑批对比、**v7 代码上线后** 成功发布推荐的一次完整记录、以及外部依赖与已知缺陷。

---

## 1. 代码版本与背景

| 项 | 说明 |
|----|------|
| 当前提交（文档编写时） | `59a3640` — `feat: v7 pipeline 架构重构 — 排名制+质量分层+并行+波段` |
| 与旧行为差异 | 同日较早调度/手动跑批在 **旧逻辑** 下为 **0 条推荐**（合成门槛未过）；拉取上述提交并 **重新部署前端 + 重启 API** 后，手动 `--force` 跑批得到 **5 条推荐**。工程需评估 **v7 阈值/过滤/质量分层** 是否 intended。 |

---

## 2. 时间线（同日）

| 顺序 | 事件 | 结果摘要 |
|------|------|----------|
| A | 调度器美东 07:30 触发（UTC 日志约 11:30） | 旧版行为：**0 推荐**（`Sit out today` / 阈值未过）；见原 [`pipeline_digest_2026-04-09.md`](pipeline_digest_2026-04-09.md) |
| B | 手动 `main.py run --market us_stock --force`（v7 前） | **0 推荐**；LLM 多数批次 success，仍合成未过线 |
| C | `git pull` 至 `59a3640`，停旧进程、`web/` npm build、重启 `main.py serve` | 新服务 + 新前端静态资源 |
| D | 再次 `main.py run --market us_stock --force` | **5 条推荐** 发布，`ref_date=20260409`，`candidates=60`，耗时约 **18 分钟** |

---

## 3. 成功跑批（D）— 关键指标

| 项 | 值 |
|----|-----|
| 命令 | `./venv/bin/python main.py run --market us_stock --force` |
| `ref_date` | `20260409` |
| 进入 Layer1 后候选规模 | **60**（`candidates: 60`） |
| **发布推荐数** | **5**（日志：`Published 5 recommendations (20260409, us_stock)`） |
| 合成侧日志（节选） | `Synthesis notes: 66 hold + 7 contradictions + 37 R:R insufficient`；`Quality tier distribution: {'medium': 8, 'low': 38}`；随后相关性过滤后仍保留可发布项 |
| 管线耗时 | 约 **18 分钟**（日志区间约 15:39–15:57，以部署机为准） |

---

## 4. 部署操作（便于复现）

1. 结束旧 `AINewsInvest` 的 `python main.py serve`（原监听 **8000**）。
2. `cd web && npm run build`（Vite 产物到 `web/dist/`）。
3. `nohup ./venv/bin/python main.py serve >> logs/serve.log 2>&1 &`（与 scheduler 同进程）。

> **未**停止：OpenClaw gateway（LLM）、QuantProject 其它进程等；若需隔离环境需单独说明。

---

## 5. 已知问题与外部依赖（建议纳入评审）

### 5.1 MarketAux

- 现象：`MarketAux free quota exhausted`（代码对 **HTTP 402** 记此日志）；亦可能出现 **429** rate limit。
- 影响：MarketAux 新闻条数减少；**不替代** Finnhub / Yahoo / Google RSS 等，但会降低「premium 源」覆盖。
- 备注：免费层 **每日额度** 以 MarketAux 控制台为准；刷新时间非本仓库实现。

### 5.2 S&P 500 成分表（维基）→ 市场宽度

- 现象：`S&P 500 fetch failed: HTTP Error 403: Forbidden`（`core/data_source.py` → `_get_sp500_components()`，使用 `pd.read_html` 拉 **维基百科** 页面，**非** SPY ETF 或交易所官方 API）。
- 影响：`_get_market_breadth` 成分列表为空时，**宽度为 0**（`breadth=0`），`market_sentiment` 缓存里 **涨跌家数统计不可信**；**主筛股**仍依赖 `data/stock_pool.json`，故推荐管线仍可跑通。
- 性质：机房 IP / 无合规 User-Agent 时，维基常 **403**，属 **站点对自动化抓取** 的限制，不是「S&P 官方 API 反爬」。

### 5.3 SEC EDGAR

- 现象：部分 ticker 请求 `efts.sec.gov` 返回 **500**。
- 影响：该标的 SEC 新闻条数可能缺失。

### 5.4 LLM（历史跑批）

- 在 **v7 前** 的日志中曾出现 `LLM request failed: timed out`（`news_sentiment_agent` 重试）。**v7 成功跑批** 未在摘录中强调超时，但 **建议** 仍监控 `analysis/llm_client.py` 超时与 `config.yaml` 中 `llm.timeout`。

### 5.5 API 错误（与管线独立）

- `GET /api/win-rate/summary` 曾出现 **500**（`core/database.py` 的 `get_win_rate_summary` 路径异常），与「当日推荐是否发布」无直接关系，但 **影响前端胜率页**；需单独修。

### 5.6 MarketAux 其它

- 跑批末尾曾出现 `MarketAux free quota exhausted`（与新闻拉取并行消耗）；与 5.1 同类。

---

## 6. 建议工程 agent 重点核对

| 主题 | 方向 |
|------|------|
| v7 行为 | 排名制、质量分层、`watch-only`、R:R 与相关性过滤与 **5 条** 的最终一致性 |
| 数据韧性 | 维基 403 → 是否改用静态成分表、备用 URL、或 yfinance 等替代 **breadth** |
| 可观测性 | 将 `_get_sp500_components` 失败率、MarketAux 402 次数打 **metrics** 或统一进 `serve.log` |
| 运营 | MarketAux 升级套餐或降低调用频率；维基请求加 **合规 User-Agent** |

---

## 7. 相关文档

- 六层流程总览：`docs/pipeline_summary.md`
- 当日早期调度摘要（0 推荐）：`docs/pipeline_digest_2026-04-09.md`
- 管线图示：`PIPELINE_FLOW.md`（仓库根目录）

---

*本文不含密钥；原始细节以部署机 `logs/serve.log` 与终端跑批输出为准。*
