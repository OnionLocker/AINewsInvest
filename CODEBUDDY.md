# Alpha Vault — CodeBuddy Code 项目上下文

> 最后更新: 2026-04-20（与 `main`/`config.yaml`/`pipeline/` 当前实现对齐）

## Permissions

All permissions are open for this project. CodeBuddy can freely:

- Read, write, and edit any files in the project
- Execute bash commands without confirmation
- Run builds, tests, and scripts
- Install dependencies
- Perform git operations (add, commit, branch, checkout, merge)
- Create and delete files and directories
- Run background tasks

## 文件编码规范

**全项目统一: UTF-8 无 BOM + LF 换行**（已在 `.editorconfig` 中强制）

- 所有文件（.py / .jsx / .yaml / .md / .json）**必须** 以 UTF-8 编码读写
- 换行符统一使用 LF（`\n`），**禁止** CRLF（Windows 默认）
- Python 文件含中文时在文件顶部保留 `# -*- coding: utf-8 -*-` 或依赖 Python 3 默认 UTF-8
- `open()` 读写文件时必须显式传 `encoding="utf-8"`，例: `open(path, "r", encoding="utf-8")`
- 前端 JS/JSX 中字符串包含中文是安全的（Vite 默认 UTF-8 输出）
- **禁止**: 用 GBK/GB2312/Latin-1 编码保存任何文件；禁止引入 BOM 头

## 项目概述

Alpha Vault v3.0.0 — US/HK 双市场 AI 投资研究系统。

- **后端**: Python 3.10+ / FastAPI / SQLite / OpenAI-compatible LLM
- **前端**: React 19 / Vite 8 / Tailwind CSS v4 / react-router-dom v7
- **入口点**:
  - CLI: `main.py` (serve / bootstrap / screen / run / build-pool / build-short-pool)
  - API: `api/server.py` → FastAPI app
  - 前端: `web/src/main.jsx` → React SPA
- **配置**: `config.yaml` (app / news_sources / llm / agent / scheduler / pipeline / stock_pool / market)

## 架构

```
AINewsInvest/
├── api/                          # FastAPI 路由层
│   ├── server.py                 # App 入口, CORS, SPA serving
│   ├── deps.py                   # 依赖注入 (JWT auth)
│   └── routes/
│       ├── auth.py               # 登录/注册      (/api/auth/*)
│       ├── admin.py              # 管理后台      (/api/admin/*)
│       ├── recommendations.py    # 推荐         (/api/recommendations/*)
│       ├── user.py               # 用户/自选股   (/api/user/*)
│       └── analysis.py           # 分析         (/api/analysis/*)
├── core/                         # 数据与领域层
│   ├── database.py               # SQLite ORM (Database 类, 所有表操作)
│   ├── models.py                 # Pydantic 数据模型
│   ├── data_source.py            # yfinance / 指数成分 / 短线池构建
│   ├── news_sources.py           # 新闻聚合 (Finnhub, MarketAux, Yahoo, RSS, SEC)
│   ├── macro_data.py             # 宏观 / 市场体制因子 (yield curve, VIX, regime flags)
│   └── user.py                   # 用户管理 (JWT, SYSTEM_DB_PATH)
├── pipeline/                     # 处理管线
│   ├── runner.py                 # 主编排器 (run_daily_pipeline, 市场隔离 + 双策略)
│   ├── screening.py              # Layer 1: 5-factor 量化筛选 (v5)
│   ├── agents.py                 # Layers 3-6: LLM Agent 管线 (核心模块, ~1.9k 行)
│   ├── analyzer.py               # 分析辅助
│   ├── evaluator.py              # 胜率评估
│   ├── backtest.py               # 回测引擎
│   ├── optimizer.py              # 参数优化
│   ├── scheduler.py              # 市场时区感知调度器
│   ├── config.py                 # 配置加载 (get_config)
│   └── skills/                   # Agent "skill" 插件
│       ├── news_skill.py         # news-edge-v3.0 (新闻情感/事件打分)
│       ├── tech_skill.py         # technical-v2   (技术面打分)
│       └── scorers.py            # 通用评分器
├── analysis/                     # 单股深度分析
│   ├── technical.py              # 技术分析 (MA, RSI, MACD, 布林带, ATR)
│   ├── fundamental.py            # 基本面分析
│   ├── valuation.py              # 估值模型
│   ├── news_fetcher.py           # 新闻抓取 + 情感分析
│   └── llm_client.py             # LLM API 客户端 (httpx, 异步)
├── web/                          # React SPA 前端
│   ├── src/
│   │   ├── pages/                # Dashboard / Recommendations / Analysis /
│   │   │                         # Screening / Watchlist / WinRate / Help /
│   │   │                         # Login / Admin
│   │   ├── components/           # Layout, RecCard, MarketSentimentPanel,
│   │   │                         # Card, Badge, Skeleton, Spinner, Toast,
│   │   │                         # ConfirmDialog, ErrorBoundary, PriceChange,
│   │   │                         # PrivateRoute
│   │   └── context/              # AuthContext (JWT 状态管理)
│   └── package.json              # React 19 + Vite 8 + Tailwind v4
├── main.py                       # CLI 入口
├── config.yaml                   # 主配置文件
└── requirements.txt              # Python 依赖
```

### 核心设计模式

- **市场隔离**: US/HK 管线完全独立，通过 `(ref_date, market)` 复合键隔离数据
- **双库架构**: `system.db` 全局数据 (推荐/胜率), per-user DB 用户级数据 (筛选/自选股)
- **6 层 Pipeline**: screening → enrichment → news_agent → tech_agent → synthesis → risk_control
- **双策略管线**: `strategy_mode = dual | short_term_only`（`short_term_only` 使用 Russell 1000 增量池）
- **市场体制检测**: 危机/熊市时自动减少或暂停推荐 (`_check_market_regime` + `core/macro_data.py`)
- **时区感知调度**: US 07:30 ET / HK 07:30 HKT，各自独立触发（任一侧 `run_time` 置空即禁用该市场自动触发）
- **Conviction 分层 (v7)**: `conviction_score = combined × (conf/100)^0.7`，按 `high / medium / low` 阈值决定是否输出交易参数
- **ATR 自适应 TP/SL (v4/v4.1)**: 有 ATR 时按倍数动态计算，失败时回退到百分比；普通/防御两套乘数按市场体制切换；含 trailing stop

## 常用命令

```bash
# === 后端 ===
python main.py serve --reload                             # 启动 API server (含调度器)
python main.py serve --port 8080                          # 指定端口
python main.py bootstrap --username admin --password xxx  # 创建管理员

python main.py screen --market us_stock --top-n 20        # Layer 1 筛选 (美股)
python main.py screen --market hk_stock                   # 港股筛选

python main.py run --market us_stock --force              # 运行完整管线 (默认 dual)
python main.py run --market us_stock --strategy short_term_only  # 仅短线 (Russell 1000)

python main.py build-pool                                 # 构建主池 (S&P500+NDX100 / HSI+HSTECH)
python main.py build-short-pool --top-n 300               # 构建短线池 (Russell 1000 增量)

# === 前端 ===
cd web && npm install                  # 安装前端依赖
cd web && npm run dev                  # 开发服务器 (localhost:5173)
cd web && npm run build                # 生产构建 → web/dist/
cd web && npm run preview              # 预览生产构建

# === 代码质量 ===
ruff check --fix .                     # Python lint + auto-fix
ruff format .                          # Python 格式化
python -m py_compile <file.py>         # 语法检查单文件

# === 健康检查 ===
curl http://localhost:8000/healthz     # API 健康状态
```

## 配置说明

| 配置项       | 位置                                    | 说明 |
|--------------|-----------------------------------------|------|
| 应用元信息   | `config.yaml` → `app.*`                 | name, version, host, port, debug |
| 新闻源       | `config.yaml` → `news_sources.*`        | finnhub_key, marketaux_key, max_per_source, max_total |
| LLM 连接     | `config.yaml` → `llm.*`                 | base_url, model, api_key, temperature, max_tokens, timeout |
| Agent 设置   | `config.yaml` → `agent.*`               | news_version, tech_version, max_retries, batch_size, fallback.* |
| 调度器       | `config.yaml` → `scheduler.*`           | enabled, us_run_time, hk_run_time（空串表示禁用该市场） |
| Screening    | `config.yaml` → `pipeline.screening.*`  | v5 5-factor 权重、最低市值/成交/换手、absolute_score 门槛、波动率拟合 |
| Synthesis    | `config.yaml` → `pipeline.synthesis.*`  | 三维权重、自适应阈值、v7 conviction 分层、各 regime 的 top_n |
| 短线         | `config.yaml` → `pipeline.short_term.*` | ATR 乘数、trailing stop、SL 上下限、防御模式参数 |
| 波段         | `config.yaml` → `pipeline.swing.*`      | 同上，持仓 10–30 天 |
| 胜率         | `config.yaml` → `pipeline.win_rate.*`   | 保留天数、自动清理 |
| 股票池       | `config.yaml` → `stock_pool.*`          | US: S&P500+NDX100, HK: HSI+HSTECH |
| 市场参数     | `config.yaml` → `market.*`              | 币种、时区、交易时段 |
| CORS         | 环境变量 `APP_CORS_ALLOW_ORIGINS`       | 逗号分隔的允许源列表 |

## 代码规范

### Python
- 日志: 使用 `loguru.logger`，不用 `print()` 或 `logging`
- HTTP: 使用 `httpx` (异步)，不用 `requests`
- 数据模型: 使用 `pydantic` BaseModel
- 类型注解: 使用 `from __future__ import annotations`，推荐添加类型提示
- 数据库: 所有操作通过 `core/database.py` 的 `Database` 类，不直接写 SQL
- 配置读取: 通过 `pipeline.config.get_config()` 获取（返回 Pydantic 模型）

### 前端
- 组件: 函数组件 + JSX，不用 class 组件
- 样式: Tailwind CSS utility classes，不写自定义 CSS
- 路由: react-router-dom v7
- 鉴权: 通过 `AuthContext` 获取 token，API 请求带 `Authorization: Bearer <token>`
- 图标: lucide-react
- 错误兜底: 顶层使用 `ErrorBoundary`，交互反馈用 `Toast` / `ConfirmDialog`

### API 路由
- 新路由放入 `api/routes/` 对应模块（auth / admin / recommendations / user / analysis）
- 在 `api/server.py` 中 `app.include_router()` 注册
- 使用 `api/deps.py` 中的依赖注入做鉴权（普通用户 `get_current_user`，管理员 `require_admin`）
- 阻塞型/CPU 密集操作用 `starlette.concurrency.run_in_threadpool` 包装

## 禁止事项

- **不要** 修改 `config.yaml` 中的 `api_key` 或其他密钥
- **不要** 在代码中硬编码 API Key 或密码
- **不要** 直接操作 `system.db` 文件，通过 Database 类访问
- **不要** 跳过市场隔离逻辑，US/HK 数据必须通过 market 参数区分
- **不要** 在同一 `ref_date`+`market` 下生成多条已发布记录（写入前先按键清理，保持幂等）
