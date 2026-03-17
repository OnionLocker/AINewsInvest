# Alpha Vault - AI 个人投研系统

基于 Flask 的 AI 驱动投资研究系统，支持 A 股 / 美股 / 港股 / 基金四大市场。从技术面、基本面、估值面、新闻面四个维度进行量化分析，结合 LLM 做综合研判，支持个股深度分析、烟蒂股资产垫评估、PDF 年报解析，并通过 Telegram 定时推送。

## 功能概览

| 模块 | 说明 |
|------|------|
| **技术面分析** | K 线数据 + MA / MACD / RSI / BOLL / KDJ / ATR 指标计算，自动识别支撑阻力位，给出入场 / 止损 / 止盈点位 |
| **基本面分析** | 多年财报采集 (akshare / yfinance)，100 分制质量评分（盈利 30 + 安全 30 + 成长 20 + 盈利质量 20），自动风险标记 |
| **估值引擎** | 四种地板价计算（净流动资产/BVPS/股息折现/悲观FCF）+ 穿透回报率 + 安全边际 + EV/EBITDA |
| **烟蒂股分析** | A 股低 PB(<1.5) 标的自动触发三层资产垫分析 (T0/T1/T2) + 10 项 Fact Check 清单 |
| **新闻情绪分析** | 自动抓取个股新闻（akshare / yfinance），基于中英文关键词库做情绪评分 |
| **LLM 深度分析** | 兼容 OpenAI API 协议，三种 Prompt（V1 基础 / V2 四维结构化 / 烟蒂股专用），支持 OpenClaw / vLLM / Ollama / ChatGPT / DeepSeek |
| **动态筛选器** | 技术面 / 基本面 / 综合三种模式，量能放大、均线突破、低估值、高分红等多维度选股 |
| **个股深度分析** | 输入代码一键分析，6 大板块完整展示，4 小时结果缓存 |
| **PDF 年报解析** | 上传 A 股年报 PDF，自动提取 7 类关键章节（受限资产/账龄/关联交易/或有事项等），LLM 辅助分析 |
| **自选管理** | TradingView 风格搜索添加，实时行情展示 |
| **定时推送** | APScheduler 调度，A 股 / 港股 / 基金 08:00 推送，美股盘前推送（自适应夏冬令时）|
| **准确率追踪** | 每条推荐自动追踪 1/3/5/10 天后实际价格，判定胜率 |
| **Dark / Light 主题** | 响应式 UI，支持移动端浏览器 |

## 项目结构

```
AINewsInvest/
├── app.py                    # Flask 主应用（路由 + API + 深度分析调度）
├── config.py                 # Flask 配置（SECRET_KEY 等）
├── config.yaml               # 应用参数配置（热重载）
├── models.py                 # 数据模型（User / Watchlist / DailyReport / RecommendationTrack / DeepAnalysisCache）
├── requirements.txt          # Python 依赖
├── gunicorn_conf.py          # Gunicorn 生产配置
├── deploy.sh                 # Ubuntu VPS 一键部署脚本
├── INTEGRATION_PLAN.md       # 集成计划文档（开发参考）
│
├── analysis/                 # AI 分析引擎（7 个模块，高内聚低耦合）
│   ├── technical.py          #   技术面：K 线 + 指标 + 入场止损止盈
│   ├── news_fetcher.py       #   新闻面：抓取 + 情绪评分
│   ├── fundamental.py        #   基本面：100 分制财务质量评分 + 风险标记
│   ├── valuation.py          #   估值面：地板价 / 穿透回报 / 安全边际 / 烟蒂股资产垫
│   ├── llm_client.py         #   LLM 接口层（V1/V2/烟蒂股 3 种 Prompt）
│   ├── pdf_parser.py         #   PDF 年报解析器（pdfplumber 提取关键章节）
│   ├── report_generator.py   #   报告生成器：调度全部模块 → 综合报告
│   ├── stock_pool.py         #   固定股票池（各市场核心标的）
│   └── stock_screener.py     #   动态筛选器（技术面 / 基本面 / 综合 3 种模式）
│
├── data/
│   ├── financial.py          #   财务报表获取（akshare / yfinance + JSON 缓存 24h）
│   ├── market_data.py        #   行情获取（实时报价 + K 线 + 缓存）
│   ├── symbols.json          #   标的数据库（build_symbol_db.py 生成）
│   └── cache/                #   财报数据缓存目录（自动创建，已 gitignore）
│
├── scripts/
│   ├── build_symbol_db.py    #   构建标的搜索数据库
│   ├── scheduler.py          #   定时推送调度器
│   └── track_accuracy.py     #   推荐准确率追踪
│
├── utils/
│   ├── config_loader.py      #   config.yaml 热重载
│   ├── crypto.py             #   Fernet 加密工具
│   ├── logger.py             #   日志系统（按日轮转）
│   └── notifier.py           #   Telegram / Webhook 推送
│
├── templates/                # Jinja2 HTML 模板
│   ├── base.html             #   基础布局（导航 + 主题切换 + 深度分析入口）
│   ├── dashboard.html        #   首页：自选 + AI 报告（含基本面/估值标签）
│   ├── deep_analysis.html    #   个股深度分析（6 板块 + PDF 上传）
│   ├── history.html          #   历史报告 + 准确率统计
│   ├── login.html            #   登录
│   ├── register.html         #   注册
│   └── settings.html         #   Telegram 推送设置
│
├── static/style.css          # CSS（Light / Dark 双主题，含基本面/估值/深度分析样式）
├── uploads/                  # PDF 上传临时目录（自动创建，已 gitignore）
├── nginx/ainews.conf         # Nginx 反向代理配置
├── systemd/ainews.service    # Systemd 服务文件
├── .env.example              # 环境变量模板
└── .gitignore
```

## 快速部署（Ubuntu VPS）

### 1. 环境要求

- Ubuntu 20.04+ / Debian 11+
- Python 3.10+
- Git

### 2. 一键部署

```bash
# 克隆项目
git clone https://github.com/OnionLocker/AINewsInvest.git
cd AINewsInvest

# 运行部署脚本（自动创建 venv、安装依赖、生成密钥、初始化数据库、启动服务）
sudo bash deploy.sh
```

部署脚本会自动完成：
- 创建 Python 虚拟环境
- 安装所有依赖（含 akshare / yfinance / pdfplumber 等）
- 生成 `SECRET_KEY` 和 `ENCRYPT_KEY` 写入 `.env`
- 初始化 SQLite 数据库（含 DeepAnalysisCache 表）
- 安装 systemd 服务并启动

### 3. 构建搜索数据库

```bash
source venv/bin/activate
python scripts/build_symbol_db.py
```

这会从 akshare 拉取 A 股 / 港股 / 基金全量标的 + 美股主要标的，生成 `data/symbols.json`。

### 4. 启动定时推送

```bash
nohup python scripts/scheduler.py > logs/scheduler.log 2>&1 &
```

推送时间表（北京时间）：
| 市场 | 时间 |
|------|------|
| A 股 / 港股 / 基金 | 08:00 |
| 美股（夏令时）| 20:30 |
| 美股（冬令时）| 21:30 |
| 准确率追踪 | 17:00 |

### 5. Nginx 配置（可选，生产环境推荐）

```bash
# 复制配置文件
sudo cp nginx/ainews.conf /etc/nginx/sites-available/ainews.conf
# 修改域名
sudo nano /etc/nginx/sites-available/ainews.conf
# 启用站点
sudo ln -s /etc/nginx/sites-available/ainews.conf /etc/nginx/sites-enabled/
# 申请 HTTPS 证书
sudo certbot --nginx -d your-domain.com
# 重载 Nginx
sudo nginx -t && sudo systemctl reload nginx
```

### 6. 日常维护

```bash
# 查看服务状态
sudo systemctl status ainews

# 查看实时日志
journalctl -u ainews -f

# 查看应用日志
tail -f logs/error.log
tail -f logs/access.log

# 重启服务
sudo systemctl restart ainews

# 更新代码后重新部署
git pull && sudo bash deploy.sh

# 手动清理过期缓存（通常无需，应用层自动管理）
rm -rf data/cache/*
```

## 配置说明

### config.yaml

```yaml
app:
  name: "Alpha Vault"
  version: "1.0"

llm:
  enabled: true                          # 是否启用 LLM 深度分析
  base_url: "http://127.0.0.1:8000"     # LLM 服务地址
  model: "openclaw-7b"                   # 模型名称
  api_key: ""                            # 本地部署通常留空
  temperature: 0.3
  max_tokens: 2048                       # V2 prompt 会自动调到 3072
  timeout: 60

fundamental:
  enabled: true                          # 是否启用基本面分析
  cache_ttl: 86400                       # 财报缓存时长（秒），默认 24h

screener:
  vol_multiplier: 2.0                    # 量能放大倍数阈值
  price_change_threshold: 3.0            # 涨跌幅异动阈值 (%)
  max_screened_per_market: 10            # 每市场最大筛选数
  pe_range: [3, 25]                      # 基本面筛选 PE 范围
  pb_range: [0.3, 3.0]                   # 基本面筛选 PB 范围
  min_roe: 5.0                           # 最低 ROE (%)
  min_dividend_yield: 2.0                # 最低股息率 (%)

tracking:
  eval_days: [1, 3, 5, 10]              # 追踪天数
  auto_expire: 30                        # 自动过期天数
```

修改 `config.yaml` 后**无需重启服务**，系统会自动热重载。

### 环境变量 (.env)

| 变量 | 说明 | 生成方式 |
|------|------|----------|
| `SECRET_KEY` | Flask 会话密钥 | `deploy.sh` 自动生成 |
| `ENCRYPT_KEY` | Fernet 对称加密密钥 | `deploy.sh` 自动生成 |

> `.env` 文件已被 `.gitignore` 排除，**不会提交到 Git**。

## 接入 LLM

本系统 LLM 接口兼容 **OpenAI API 协议**，支持任何提供 `/v1/chat/completions` 端点的服务。

### 支持的 LLM 后端

| 后端 | base_url 示例 | 说明 |
|------|-------------|------|
| **OpenClaw** | `http://127.0.0.1:8000` | 本地部署，推荐 |
| **vLLM** | `http://127.0.0.1:8000` | 高性能推理 |
| **Ollama** | `http://127.0.0.1:11434` | 简单易用 |
| **ChatGPT** | `https://api.openai.com` | 需要 api_key |
| **DeepSeek** | `https://api.deepseek.com` | 需要 api_key |

### 验证连通性

```
GET /api/llm/status
```

返回示例：

```json
{
  "available": true,
  "model": "openclaw-7b",
  "base_url": "http://127.0.0.1:8000",
  "error": null
}
```

### LLM 三种 Prompt 模式

| 模式 | 触发条件 | Token 消耗 | 说明 |
|------|----------|------------|------|
| V1 基础 | 无基本面/估值数据时 | ~2048 | 技术面 + 新闻面分析 |
| V2 结构化 | 有基本面或估值数据时 | ~3072 | 四维分析框架（定性/财务/估值/结论）|
| 烟蒂股专用 | A 股 + PB<1.5 + 深度分析 | ~3072 | 三支柱 + 10 项 Fact Check |

未启用 LLM 时系统正常运行，使用关键词情绪分析作为替代。

## API 端点

### 基础

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/llm/status` | LLM 连通性检查 |

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/register` | 注册 |
| GET/POST | `/login` | 登录 |
| GET | `/logout` | 登出 |

### 自选

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/search?q=茅台` | 标的搜索（模糊匹配） |
| GET | `/api/watchlist` | 获取自选列表 |
| POST | `/api/watchlist` | 添加自选 `{ticker, name, market}` |
| DELETE | `/api/watchlist/<id>` | 删除自选 |
| GET | `/api/watchlist/quotes` | 自选实时行情 |

### 报告

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/report?market=a_share&date=2026-03-11` | 获取指定日期报告 |
| GET | `/api/report/history?market=a_share` | 历史报告列表 |
| POST | `/api/report/generate` | 手动生成报告 `{market}` |
| GET | `/api/accuracy?market=a_share` | 推荐准确率统计 |

### 深度分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/deep-analysis` | 个股深度分析 `{ticker, market, force?}` |
| POST | `/api/upload-report` | 上传年报 PDF，form-data `pdf` 字段 |

> `force: true` 可跳过 4 小时缓存强制重新分析。

## 数据库模型

| 模型 | 表名 | 说明 |
|------|------|------|
| `User` | `users` | 用户账号 + Telegram 加密配置 |
| `Watchlist` | `watchlist` | 用户自选标的 |
| `DailyReport` | `daily_reports` | 每日报告 (JSON)，按市场+日期唯一 |
| `RecommendationTrack` | `recommendation_tracks` | 推荐追踪（自动回填 N 天后价格）|
| `DeepAnalysisCache` | `deep_analysis_cache` | 深度分析缓存（4h TTL）|

## 技术栈

- **后端**: Python 3.10+ / Flask / SQLAlchemy / APScheduler
- **数据**: akshare (A 股 / 港股 / 基金) / yfinance (美股 / 港股)
- **分析**: numpy / pandas / 自研技术指标引擎 / 基本面评分 / 估值引擎
- **PDF**: pdfplumber（年报解析）
- **LLM**: OpenAI API 兼容接口（3 种 Prompt 模式）
- **前端**: Bootstrap 5 / Bootstrap Icons / 原生 JS / CSS Variables 双主题
- **部署**: Gunicorn / Nginx / Systemd / Let's Encrypt
- **安全**: Fernet 加密 / werkzeug 密码哈希 / Flask-Login 会话管理

## 故障排查

| 问题 | 排查方法 |
|------|----------|
| 服务无法启动 | `journalctl -u ainews -f` 查看错误日志 |
| 报告生成失败 | `tail -f logs/error.log` 检查分析模块报错 |
| LLM 不可用 | 访问 `/api/llm/status` 检查连通性 |
| 行情数据为空 | 检查 akshare/yfinance 是否可用，确认网络正常 |
| 基本面数据缺失 | 检查 `config.yaml` 中 `fundamental.enabled` 是否为 `true` |
| PDF 解析失败 | 确认已安装 `pdfplumber`，检查 PDF 文件是否损坏 |
| 搜索无结果 | 执行 `python scripts/build_symbol_db.py` 重建标的库 |
| 推送未收到 | 在设置页检查 Telegram Bot Token 和 Chat ID 是否正确 |

## License

MIT
