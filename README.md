# Alpha Vault - AI 个人投研系统

基于 Flask 的 AI 驱动投资研究系统，支持 A 股 / 美股 / 港股 / 基金四大市场的技术面分析、新闻情绪分析和 LLM 深度分析，提供入场 / 止损 / 止盈点位建议，并通过 Telegram 定时推送。

## 功能概览

| 模块 | 说明 |
|------|------|
| **技术面分析** | K 线数据 + MA / MACD / RSI / BOLL / KDJ / ATR 指标计算，自动识别支撑阻力位，给出入场 / 止损 / 止盈点位 |
| **新闻情绪分析** | 自动抓取个股新闻（akshare / yfinance），基于中英文关键词库做情绪评分 |
| **LLM 深度分析** | 兼容 OpenAI API 协议，支持 OpenClaw / vLLM / Ollama / ChatGPT / DeepSeek |
| **动态异动筛选** | 量能放大、均线突破、RSI 极端、MACD 交叉等多维度自动选股 |
| **自选管理** | TradingView 风格搜索添加，实时行情展示 |
| **定时推送** | APScheduler 调度，A 股 / 港股 / 基金 08:00 推送，美股盘前推送（自适应夏冬令时）|
| **准确率追踪** | 每条推荐自动追踪 1/3/5/10 天后实际价格，判定胜率 |
| **Dark / Light 主题** | 响应式 UI，支持移动端浏览器 |

## 项目结构

```
AINewsInvest/
├── app.py                    # Flask 主应用（路由 + API）
├── config.py                 # Flask 配置（SECRET_KEY 等）
├── config.yaml               # 应用参数配置（热重载）
├── models.py                 # 数据模型（User / Watchlist / DailyReport / RecommendationTrack）
├── requirements.txt          # Python 依赖
├── gunicorn_conf.py          # Gunicorn 生产配置
├── deploy.sh                 # Ubuntu VPS 一键部署脚本
│
├── analysis/                 # AI 分析引擎
│   ├── technical.py          #   技术面：K 线 + 指标 + 入场止损止盈
│   ├── news_fetcher.py       #   新闻面：抓取 + 情绪评分
│   ├── report_generator.py   #   报告生成器：综合分析 + 排序
│   ├── stock_pool.py         #   固定股票池（各市场核心标的）
│   ├── stock_screener.py     #   动态异动筛选器
│   └── llm_client.py         #   LLM 接口层（OpenAI API 兼容）
│
├── data/
│   ├── market_data.py        #   行情获取（akshare / yfinance + 缓存）
│   └── symbols.json          #   标的数据库（build_symbol_db.py 生成）
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
│   ├── base.html             #   基础布局（导航 + 主题切换）
│   ├── dashboard.html        #   首页：自选 + AI 报告
│   ├── history.html          #   历史报告 + 准确率统计
│   ├── login.html            #   登录
│   ├── register.html         #   注册
│   └── settings.html         #   Telegram 推送设置
│
├── static/style.css          # CSS（Light / Dark 双主题）
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
- 安装所有依赖
- 生成 `SECRET_KEY` 和 `ENCRYPT_KEY` 写入 `.env`
- 初始化 SQLite 数据库
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

### 5. 日常维护

```bash
# 查看服务状态
sudo systemctl status ainews

# 查看日志
journalctl -u ainews -f

# 重启服务
sudo systemctl restart ainews

# 更新代码后重新部署
git pull && sudo bash deploy.sh
```

## 接入 OpenClaw / LLM

本系统 LLM 接口兼容 **OpenAI API 协议**，支持任何提供 `/v1/chat/completions` 端点的服务。

### 配置方法

编辑 `config.yaml`：

```yaml
llm:
  enabled: true
  base_url: "http://127.0.0.1:8000"   # OpenClaw / vLLM 地址
  model: "openclaw-7b"                  # 模型名称
  api_key: ""                           # 本地部署通常留空
  temperature: 0.3
  max_tokens: 2048
  timeout: 60
```

### 支持的 LLM 后端

| 后端 | base_url 示例 | 说明 |
|------|-------------|------|
| **OpenClaw** | `http://127.0.0.1:8000` | 本地部署，推荐 |
| **vLLM** | `http://127.0.0.1:8000` | 高性能推理 |
| **Ollama** | `http://127.0.0.1:11434` | 简单易用 |
| **ChatGPT** | `https://api.openai.com` | 需要 api_key |
| **DeepSeek** | `https://api.deepseek.com` | 需要 api_key |

### 验证连通性

启动应用后访问：

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

### LLM 在系统中的作用

启用 LLM 后，每次生成报告时：

1. 先完成技术面分析（MA / MACD / RSI 等指标 + 入场止损止盈计算）
2. 先完成新闻情绪分析（关键词评分）
3. 将技术面数据 + 新闻列表发送给 LLM，获取 **深度综合分析**
4. LLM 分析结果会显示在报告卡片中，并影响综合置信度评分

未启用 LLM 时系统正常运行，使用关键词情绪分析作为替代。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/search?q=茅台&market=a_share` | 标的搜索 |
| GET | `/api/watchlist` | 获取自选列表 |
| POST | `/api/watchlist` | 添加自选 |
| DELETE | `/api/watchlist/<id>` | 删除自选 |
| GET | `/api/watchlist/quotes` | 自选实时行情 |
| GET | `/api/report?market=a_share&date=2026-03-11` | 获取报告 |
| GET | `/api/report/history?market=a_share` | 历史报告列表 |
| POST | `/api/report/generate` | 手动生成报告 |
| GET | `/api/accuracy?market=a_share` | 准确率统计 |
| GET | `/api/llm/status` | LLM 连通性检查 |

## 技术栈

- **后端**: Python 3.10+ / Flask / SQLAlchemy / APScheduler
- **数据**: akshare (A 股 / 港股 / 基金) / yfinance (美股)
- **分析**: numpy / pandas / 自研技术指标引擎
- **LLM**: OpenAI API 兼容接口
- **前端**: Bootstrap 5 / 原生 JS / CSS Variables 主题
- **部署**: Gunicorn / Nginx / Systemd
- **安全**: Fernet 加密 / werkzeug 密码哈希 / Flask-Login 会话管理

## 配置说明

| 文件 | 用途 | 备注 |
|------|------|------|
| `.env` | 敏感信息（密钥） | `deploy.sh` 自动生成，**不要提交 Git** |
| `config.yaml` | 应用参数 | 支持热重载，修改后无需重启 |
| `config.py` | Flask 配置 | 从 `.env` 读取密钥 |

## License

MIT
