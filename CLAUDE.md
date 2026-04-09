# Alpha Vault — Claude Code 项目上下文

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
  - CLI: `main.py` (serve / bootstrap / screen / run / build-pool)
  - API: `api/server.py` → FastAPI app
  - 前端: `web/src/main.jsx` → React SPA
- **配置**: `config.yaml` (LLM / agent / scheduler / pipeline / stock_pool / market)

## 架构

```
AINewsInvest/
├── api/                   # FastAPI 路由层
│   ├── server.py          # App 入口, CORS, SPA serving
│   ├── deps.py            # 依赖注入 (JWT auth)
│   └── routes/            # 路由模块
│       ├── auth.py        # 登录/注册 (/api/auth/*)
│       ├── admin.py       # 管理后台 (/api/admin/*)
│       ├── recommendations.py  # 推荐 (/api/recommendations/*)
│       ├── user.py        # 用户操作 (/api/user/*)
│       └── analysis.py    # 分析 (/api/analysis/*)
├── core/                  # 数据层
│   ├── database.py        # SQLite ORM (Database 类, 所有表操作)
│   ├── models.py          # Pydantic 数据模型
│   ├── data_source.py     # 市场数据源 (yfinance, index components)
│   ├── news_sources.py    # 新闻源 (Finnhub, MarketAux, Yahoo, RSS, SEC)
│   └── user.py            # 用户管理 (JWT, SYSTEM_DB_PATH)
├── pipeline/              # 6 层处理管线
│   ├── runner.py          # 主编排器 (run_daily_pipeline)
│   ├── screening.py       # Layer 1: 量化筛选
│   ├── agents.py          # Layers 3-6: LLM Agent 管线 (1227行, 核心模块)
│   ├── analyzer.py        # 分析辅助
│   ├── evaluator.py       # 胜率评估
│   ├── backtest.py        # 回测引擎 (~520行)
│   ├── optimizer.py       # 参数优化
│   ├── scheduler.py       # 市场时区感知调度器
│   └── config.py          # 配置加载 (get_config)
├── analysis/              # 分析模块
│   ├── technical.py       # 技术分析 (MA, RSI, MACD, 布林带)
│   ├── fundamental.py     # 基本面分析
│   ├── valuation.py       # 估值模型
│   ├── news_fetcher.py    # 新闻抓取 + 情感分析
│   └── llm_client.py      # LLM API 客户端
├── web/                   # React SPA 前端
│   ├── src/
│   │   ├── pages/         # 页面组件 (Dashboard, Recommendations, Analysis, etc.)
│   │   ├── components/    # 通用组件 (Card, Badge, Spinner, RecCard, etc.)
│   │   └── context/       # AuthContext (JWT 状态管理)
│   └── package.json       # React 19 + Vite 8 + Tailwind v4
├── main.py                # CLI 入口
├── config.yaml            # 主配置文件
└── requirements.txt       # Python 依赖
```

### 核心设计模式

- **市场隔离**: US/HK 管线完全独立，通过 `(ref_date, market)` 复合键隔离数据
- **双库架构**: `system.db` 全局数据 (推荐/胜率), per-user DB 用户级数据 (筛选/自选股)
- **6 层 Pipeline**: screening → enrichment → news_agent → tech_agent → synthesis → risk_control
- **市场体制检测**: 危机/熊市时自动减少或暂停推荐 (`_check_market_regime`)
- **时区感知调度**: US 07:30 ET / HK 07:30 HKT，各自独立触发

## 常用命令

```bash
# === 后端 ===
python main.py serve --reload          # 启动 API server (含调度器)
python main.py serve --port 8080       # 指定端口
python main.py bootstrap --username admin --password xxx  # 创建管理员
python main.py screen --market us_stock --top-n 20        # Layer 1 筛选
python main.py screen --market hk_stock                   # 港股筛选
python main.py run --market us_stock --force              # 运行完整管线
python main.py build-pool                                 # 构建股票池

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

| 配置项 | 位置 | 说明 |
|--------|------|------|
| LLM 连接 | `config.yaml` → `llm.*` | base_url, model, api_key, temperature |
| Agent 设置 | `config.yaml` → `agent.*` | 6 层管线参数, fallback 规则 |
| 调度器 | `config.yaml` → `scheduler.*` | enabled, us/hk_run_time |
| Pipeline | `config.yaml` → `pipeline.*` | 筛选/综合/短线/波段 参数 |
| 股票池 | `config.yaml` → `stock_pool.*` | US: S&P500+NDX100, HK: HSI+HSTECH |
| CORS | 环境变量 `APP_CORS_ALLOW_ORIGINS` | 逗号分隔的允许源列表 |

## 代码规范

### Python
- 日志: 使用 `loguru.logger`，不用 `print()` 或 `logging`
- HTTP: 使用 `httpx` (异步)，不用 `requests`
- 数据模型: 使用 `pydantic` BaseModel
- 类型注解: 使用 `from __future__ import annotations`，推荐添加类型提示
- 数据库: 所有操作通过 `core/database.py` 的 `Database` 类，不直接写 SQL
- 配置读取: 通过 `pipeline.config.get_config()` 获取

### 前端
- 组件: 函数组件 + JSX，不用 class 组件
- 样式: Tailwind CSS utility classes，不写自定义 CSS
- 路由: react-router-dom v7
- 鉴权: 通过 `AuthContext` 获取 token，API 请求带 `Authorization: Bearer <token>`
- 图标: lucide-react

### API 路由
- 新路由放入 `api/routes/` 对应模块
- 在 `api/server.py` 中 `app.include_router()` 注册
- 使用 `api/deps.py` 中的依赖注入做鉴权

## 禁止事项

- **不要** 修改 `config.yaml` 中的 `api_key` 或其他密钥
- **不要** 在代码中硬编码 API Key 或密码
- **不要** 直接操作 `system.db` 文件，通过 Database 类访问
- **不要** 跳过市场隔离逻辑，US/HK 数据必须通过 market 参数区分
