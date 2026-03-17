# Alpha Vault × 龟龟/烟蒂框架 整合技术方案

> 本文档为持久化技术方案，供跨会话实施时参考。  
> 已完成的任务打 `[x]`，未完成打 `[ ]`。  
> 最后更新：2026-03-13

---

## 一、现状摘要

### 1.1 Alpha Vault 现有能力

| 维度 | 实现 | 代码位置 |
|------|------|----------|
| 技术面分析 | MA/MACD/RSI/BOLL/KDJ/ATR + 支撑阻力 + 入场止损止盈 | `analysis/technical.py` → `analyze()` |
| 新闻情绪 | akshare/yfinance 抓取 + 中英文关键词评分 | `analysis/news_fetcher.py` → `analyze_sentiment()` |
| LLM 深度分析 | OpenAI 兼容接口，传入技术面+新闻做综合分析 | `analysis/llm_client.py` → `llm_analyze_stock()` |
| 异动筛选 | 涨跌幅/放量/均线突破/RSI极端/MACD交叉 | `analysis/stock_screener.py` → `screen_market()` |
| 报告生成 | 技术面+新闻+LLM → 置信度排序 → 报告JSON | `analysis/report_generator.py` → `generate_report()` |
| 行情数据 | akshare(A/港/基金) + yfinance(美股)，60s TTL缓存 | `data/market_data.py` → `get_quote()` |
| 准确率追踪 | 1/3/5/10 天后回填价格，判定 win/loss/partial | `scripts/track_accuracy.py` |
| 定时推送 | APScheduler，A/港 08:00，美股 20:30/21:30 | `scripts/scheduler.py` |

### 1.2 现有数据流

```
stock_pool.get_pool(market) + stock_screener.screen_market(market)
    ↓
report_generator._analyze_one(ticker, name, market, use_llm)
    ├── technical.analyze(ticker, market)        → tech dict
    ├── news_fetcher.fetch_news(ticker, market)  → news list
    ├── news_fetcher.analyze_sentiment(news)     → sentiment dict
    └── llm_client.llm_analyze_stock(...)        → llm_summary str
    ↓
items sorted by confidence → DailyReport.data (JSON) → Telegram 推送
```

### 1.3 核心短板（整合目标）

| 短板 | 说明 |
|------|------|
| **无基本面数据** | 不拉财报（利润表/资产负债表/现金流），无法做基本面分析 |
| **无估值能力** | 只有技术面入场止损止盈，无 PB/PE/FCF/穿透回报率等估值 |
| **筛选器纯技术面** | 只做技术异动，无法发现被低估的价值标的 |
| **LLM Prompt 浅** | 只传技术面+新闻标题，缺少结构化分析框架 |
| **无个股深度研究** | 只有批量报告，无法对单只股票做完整研究 |

---

## 二、整合方案总览

```
                    ┌──────────────────────────────────────────────┐
                    │           Phase 1: 基本面数据层               │
                    │  analysis/fundamental.py + data/financial.py  │
                    └──────────────┬───────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │ Phase 2: 估值引擎│  │ Phase 3: 筛选升级│  │ Phase 4: LLM增强│
    │ analysis/        │  │ stock_screener   │  │ llm_client       │
    │ valuation.py     │  │ .py 改造         │  │ .py prompt升级   │
    └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
             │                    │                    │
             └────────────────────┼────────────────────┘
                                  ▼
                    ┌──────────────────────────────────┐
                    │ Phase 5: 报告结构升级 + 深度分析API │
                    │ report_generator.py + app.py      │
                    └──────────────────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────────────┐
                    │ Phase 6: 前端展示 + PDF年报(可选)   │
                    │ templates/ + pdf_parser.py         │
                    └──────────────────────────────────┘
```

---

## 三、Phase 1: 基本面数据采集层

**目标**：为系统增加财务报表数据获取能力，作为后续估值/筛选/LLM的数据基础。

### 3.1 新建 `data/financial.py` — 财务数据获取

- [x] **3.1.1** 创建 `data/financial.py`

```python
"""
data/financial.py - 财务报表数据获取层

A股: akshare 接口 (免费, 无需token)
美股: yfinance
港股: akshare / yfinance fallback

缓存策略: 财报数据变动频率低, TTL = 24h, 存 Parquet 文件到 data/cache/
"""

# ━━ 公开接口 ━━

def get_financial_data(ticker: str, market: str, years: int = 5) -> dict | None:
    """
    获取指定标的近 N 年的财务数据。

    返回:
    {
        "ticker": str,
        "market": str,
        "income": pd.DataFrame,         # 利润表 (columns: 年度, 营业收入, 净利润, 扣非净利润, 毛利率, ...)
        "balance": pd.DataFrame,        # 资产负债表 (columns: 年度, 总资产, 净资产, 总负债, 流动资产, ...)
        "cashflow": pd.DataFrame,       # 现金流量表 (columns: 年度, 经营现金流, 投资现金流, 筹资现金流, FCF, ...)
        "dividend": pd.DataFrame,       # 分红历史 (columns: 年度, 每股股利, 分红率, ...)
        "key_ratios": {                 # 关键财务比率 (最新年度)
            "roe": float,              # 净资产收益率
            "roa": float,              # 总资产收益率
            "gross_margin": float,     # 毛利率
            "net_margin": float,       # 净利率
            "debt_ratio": float,       # 资产负债率
            "current_ratio": float,    # 流动比率
            "fcf_yield": float,        # 自由现金流收益率 (FCF / 市值)
            "dividend_yield": float,   # 股息率 (TTM)
            "pb": float,              # 市净率
            "pe_ttm": float,          # 滚动市盈率
            "ev_ebitda": float,       # EV/EBITDA
            "non_recurring_pct": float, # 非经常性损益占比
        }
    }
    """
```

- [x] **3.1.2** A 股财报获取（akshare 接口）

```python
# 使用以下 akshare 接口:
# - ak.stock_financial_report_sina(stock=ticker, symbol="利润表")  → 利润表
# - ak.stock_financial_report_sina(stock=ticker, symbol="资产负债表") → 资产负债表
# - ak.stock_financial_report_sina(stock=ticker, symbol="现金流量表") → 现金流量表
# 或者使用更稳定的:
# - ak.stock_financial_analysis_indicator(symbol=ticker) → 财务指标汇总
# - ak.stock_profit_forecast_em(symbol=ticker) → 盈利预测
# - ak.stock_history_dividend_detail(symbol=ticker, indicator="分红") → 分红历史

def _financial_a_share(ticker: str, years: int) -> dict: ...
```

- [x] **3.1.3** 美股财报获取（yfinance 接口）

```python
# yfinance 提供:
# - Ticker.financials       → 利润表
# - Ticker.balance_sheet    → 资产负债表
# - Ticker.cashflow         → 现金流量表
# - Ticker.dividends        → 分红历史
# - Ticker.info             → PE/PB/marketCap 等

def _financial_us(ticker: str, years: int) -> dict: ...
```

- [x] **3.1.4** 港股财报获取

```python
# 港股优先用 akshare, fallback 到 yfinance
# - ak.stock_financial_hk_report_em(symbol=ticker) 或 yfinance
def _financial_hk(ticker: str, years: int) -> dict: ...
```

- [x] **3.1.5** Parquet 磁盘缓存

```python
# 参考龟龟框架 ScreenerCache 设计
# 缓存路径: data/cache/{market}_{ticker}_financial.parquet
# TTL: 24小时 (财报数据日内不变)
# 好处: 避免重复 API 调用, 加快报告生成速度

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
FINANCIAL_CACHE_TTL = 86400  # 24小时

def _get_cached(ticker: str, market: str) -> dict | None: ...
def _set_cached(ticker: str, market: str, data: dict): ...
```

### 3.2 新建 `analysis/fundamental.py` — 基本面分析

- [x] **3.2.1** 创建 `analysis/fundamental.py`

```python
"""
analysis/fundamental.py - 基本面分析引擎

输入: data/financial.py 返回的财务数据
输出: 基本面分析结论 + 关键指标摘要

参考: 龟龟框架 Phase 3 的四因子模型中的财务质量检查
"""

def analyze_fundamental(ticker: str, market: str) -> dict | None:
    """
    返回:
    {
        "ticker": str,
        "market": str,
        "quality_score": int,       # 0-100 财务质量评分
        "quality_label": str,       # "优秀" / "良好" / "一般" / "较差"
        "growth": {                 # 成长性
            "revenue_growth_3y": float,   # 近3年营收复合增长率
            "profit_growth_3y": float,    # 近3年净利润复合增长率
            "trend": str,                 # "加速增长" / "稳定增长" / "放缓" / "下滑"
        },
        "profitability": {          # 盈利能力
            "roe": float,
            "roe_trend": str,             # "改善" / "稳定" / "恶化"
            "gross_margin": float,
            "net_margin": float,
        },
        "safety": {                 # 安全性
            "debt_ratio": float,
            "current_ratio": float,
            "fcf_positive_years": int,    # 近5年FCF为正的年数
            "dividend_continuous_years": int,  # 连续分红年数
        },
        "valuation_snapshot": {     # 估值快照
            "pe_ttm": float,
            "pb": float,
            "dividend_yield": float,
            "ev_ebitda": float,
        },
        "risk_flags": list[str],    # 风险标记列表
        "fundamental_summary": str, # 人话总结 (类似 tech_summary)
    }
    """
```

- [x] **3.2.2** 财务质量评分逻辑

```python
# 参考龟龟框架 screener_core.py 的 _check_financial_quality:
#
# 评分维度 (总分 100):
#   ROE > 8%: +20, ROE > 15%: +30                    (30分)
#   毛利率 > 20%: +10, > 40%: +15                    (15分)
#   负债率 < 60%: +10, < 40%: +15                    (15分)
#   扣非净利润占比 > 70%: +10                          (10分)
#   FCF连续3年为正: +10, 5年: +15                     (15分)
#   连续分红 >= 3年: +10, >= 5年: +15                  (15分)
#
# 风险标记 (risk_flags):
#   - "ROE连续下滑" (近3年ROE逐年下降)
#   - "高负债" (负债率 > 70%)
#   - "现金流枯竭" (最近2年经营现金流为负)
#   - "非经常性损益占比过高" (> 50%)
#   - "未分红" (最近3年无分红)
```

- [x] **3.2.3** 生成 `fundamental_summary` 人话总结

```python
def _build_fundamental_summary(data: dict) -> str:
    """
    类似 technical.py 的 _build_summary, 生成基本面分析文字总结。
    示例: "盈利能力优秀，近3年ROE均在15%以上且稳中有升。资产负债率42%，
           财务结构稳健。连续5年正向自由现金流，分红持续性好。当前PE(TTM)12.3倍，
           PB 1.8倍，估值处于历史中低位。"
    """
```

### 3.3 config.yaml 新增配置

- [x] **3.3.1** 在 `config.yaml` 增加基本面分析配置

```yaml
# 基本面分析
fundamental:
  enabled: true                 # 是否启用基本面分析
  cache_ttl: 86400              # 财务数据缓存TTL（秒），默认24小时
  data_source: "akshare"        # 主数据源: akshare / tushare
  tushare_token: ""             # (可选) Tushare Pro token, 数据质量更高
```

### 3.4 requirements.txt 新增依赖

- [x] **3.4.1** 添加依赖

```
pyarrow>=14.0.0    # Parquet 缓存
tushare>=1.4.0     # (可选) Tushare Pro 数据源
```

---

## 四、Phase 2: 估值引擎

**目标**：为系统增加多维度估值能力，给出"值不值这个价"的判断。

### 4.1 新建 `analysis/valuation.py`

- [x] **4.1.1** 创建 `analysis/valuation.py`

```python
"""
analysis/valuation.py - 估值引擎

参考龟龟框架的估值模型:
  - 地板价 (5种方法)
  - 穿透回报率 (Owner Earnings)
  - EV/EBITDA
  - PB-ROE联合估值

参考烟蒂股框架的:
  - 资产垫 (Asset Cushion) T0/T1/T2
  - 低维护CAPEX判定
"""

def valuate(ticker: str, market: str,
            financial_data: dict, current_price: float,
            shares_outstanding: float) -> dict | None:
    """
    返回:
    {
        "ticker": str,
        "market": str,
        "floor_price": {               # 地板价估值 (参考龟龟 screener_core.py)
            "net_current_asset": float, # 方法1: 净流动资产/股
            "bvps": float,             # 方法2: 每股净资产
            "ten_year_low": float,     # 方法3: 10年最低价
            "dividend_discount": float, # 方法4: 股息折现价
            "pessimistic_fcf": float,  # 方法5: 悲观FCF资本化
            "average": float,          # 5种方法平均
        },
        "penetration_return": {        # 穿透回报率 (龟龟核心)
            "owner_earnings": float,    # 股东盈余 = 净利润 + 折旧 - 维护性CAPEX
            "rate": float,             # 穿透回报率 = owner_earnings / 市值
            "grade": str,              # "A" (>15%) / "B" (8-15%) / "C" (<8%)
        },
        "ev_ebitda": {
            "value": float,
            "percentile": str,         # 历史百分位: "低估" / "合理" / "偏高"
        },
        "safety_margin": {             # 安全边际
            "current_price": float,
            "floor_price": float,
            "margin_pct": float,       # (floor - current) / current * 100
            "verdict": str,            # "充足" (>30%) / "适中" (10-30%) / "不足" (<10%) / "溢价"
        },
        "valuation_summary": str,      # 人话总结
    }
    """
```

- [x] **4.1.2** 地板价计算（5种方法）

```python
# 参考龟龟框架 screener_core.py 的 5 种 Floor Price 方法:
#
# 1. 净流动资产/股 = (流动资产 - 总负债) / 总股本
# 2. BVPS = 净资产 / 总股本
# 3. 10年最低价 = 10年周K最低价
# 4. 股息折现 = 近3年平均每股股利 / 无风险利率
# 5. 悲观FCF资本化 = 近3年最低FCF / (无风险利率 + 3%)
# 平均地板价 = 5种方法的平均值

def _calc_floor_price(financial_data: dict, ticker: str, market: str) -> dict: ...
```

- [x] **4.1.3** 穿透回报率计算

```python
# 参考龟龟框架 Phase 3 Prompt 的穿透回报率:
#
# 股东盈余 (Owner Earnings):
#   = 净利润 + 折旧摊销 - 维护性资本开支
#   维护性资本开支 ≈ 折旧摊销 × 0.7 (保守估计)
#   或 = min(资本开支, 折旧摊销) 如果能区分维护性/扩张性
#
# 穿透回报率 R = Owner Earnings / 当前总市值
#   R > 15%: A级 (极具吸引力)
#   R = 8%-15%: B级 (合理偏低估)
#   R < 8%: C级 (估值偏高或一般)

def _calc_penetration_return(financial_data: dict, market_cap: float) -> dict: ...
```

- [x] **4.1.4** 安全边际计算

```python
# 安全边际 = (地板价平均 - 当前价) / 当前价 × 100%
#   > 30%: 充足 → 适合建仓
#   10%-30%: 适中 → 可以关注
#   0-10%: 不足 → 谨慎
#   < 0%: 溢价 → 不建议
```

- [x] **4.1.5** 烟蒂股资产垫分析（可选，A股增强）

```python
# 参考烟蒂股 Prompt 的资产垫体系:
# T0: 净有息负债 / EBITDA < 3
# T1: (现金+短期投资 - 有息负债) / 市值
# T2: (净流动资产 - 总负债) / 市值 (Ben Graham 公式)
#
# 仅在 market=="a_share" 且 PB<1.5 时计算，用于识别深度价值标的

def _cigbutt_asset_cushion(financial_data: dict, market_cap: float) -> dict | None: ...
```

---

## 五、Phase 3: 筛选器升级

**目标**：在现有技术面异动筛选基础上，增加基本面/估值维度筛选。

### 5.1 改造 `analysis/stock_screener.py`

- [x] **5.1.1** 新增筛选模式参数

```python
# 现有: screen_market(market) → 纯技术面异动
# 新增: screen_market(market, mode="technical"|"fundamental"|"combined")
#   - "technical": 现有逻辑不变
#   - "fundamental": 基本面价值筛选 (新增)
#   - "combined": 技术面+基本面综合筛选 (新增)

def screen_market(market: str, mode: str = "technical") -> list[tuple[str, str, str]]:
    if mode == "technical":
        return _screen_technical(market)        # 现有逻辑
    elif mode == "fundamental":
        return _screen_fundamental(market)      # 新增
    elif mode == "combined":
        return _screen_combined(market)         # 新增
```

- [x] **5.1.2** 基本面筛选逻辑（Tier 1 粗筛）

```python
# 参考龟龟框架 screener_core.py 的 _tier1_filter:
#
# 排除条件:
#   - ST / *ST / PT 标的
#   - 上市不满 2 年
#   - 市值 < 10亿
#
# 初筛条件 (满足至少3项):
#   - PE(TTM) 在 3-25 之间
#   - PB 在 0.3-3 之间
#   - 股息率(TTM) > 2%
#   - ROE > 8%
#
# 排名公式 (参考龟龟):
#   composite = 0.4 × 股息率 + 0.3 × (1/PE) + 0.3 × (1/PB)
#   取前 MAX_SCREENED 名

def _screen_fundamental(market: str) -> list[tuple[str, str, str]]: ...
```

- [x] **5.1.3** 基本面筛选 Tier 2 精筛

```python
# 对 Tier 1 结果做深度检查:
#
# 硬否决 (hard veto, 参考龟龟 _check_hard_vetoes):
#   - 股权质押率 > 50%  → 排除
#   - 审计意见非"标准无保留" → 排除
#
# 财务质量检查 (参考龟龟 _check_financial_quality):
#   - ROE < 5% 连续2年 → 降权
#   - 经营现金流连续2年为负 → 降权
#   - 负债率 > 70% → 降权
#
# 综合评分 (参考龟龟 Tier2 composite):
#   ROE (20%) + FCF收益率 (20%) + 穿透回报率 (25%) + EV/EBITDA逆序 (15%) + 地板价溢价逆序 (20%)

def _tier2_deep_check(candidates: list, market: str) -> list[tuple[str, str, str]]: ...
```

- [x] **5.1.4** 从 `config.yaml` 读取筛选参数

```python
# 当前 stock_screener.py 硬编码了参数 (VOL_MULTIPLIER=2.0 等)
# 改为从 config.yaml 读取:
from utils.config_loader import get_config

def _get_screener_config():
    cfg = get_config()
    sc = cfg.get("screener", {})
    return {
        "vol_multiplier": sc.get("vol_multiplier", 2.0),
        "price_change_threshold": sc.get("price_change_threshold", 3.0),
        "max_screened": sc.get("max_screened_per_market", 10),
        # Phase 3 新增
        "min_market_cap": sc.get("min_market_cap", 10),    # 亿
        "pe_range": sc.get("pe_range", [3, 25]),
        "pb_range": sc.get("pb_range", [0.3, 3.0]),
        "min_dividend_yield": sc.get("min_dividend_yield", 2.0),
        "min_roe": sc.get("min_roe", 8.0),
    }
```

### 5.2 config.yaml 筛选参数扩展

- [x] **5.2.1** 新增基本面筛选配置

```yaml
screener:
  # 现有技术面参数
  vol_multiplier: 2.0
  price_change_threshold: 3.0
  max_screened_per_market: 10
  # 新增基本面筛选参数
  fundamental_enabled: true
  min_market_cap: 10            # 最小市值(亿元)
  pe_range: [3, 25]             # PE(TTM) 范围
  pb_range: [0.3, 3.0]          # PB 范围
  min_dividend_yield: 2.0       # 最低股息率(%)
  min_roe: 8.0                  # 最低ROE(%)
  max_pledge_ratio: 50          # 股权质押率上限(%)
```

---

## 六、Phase 4: LLM Prompt 增强

**目标**：将 LLM 从"自由发挥"升级为"结构化多因子分析框架"。

### 6.1 改造 `analysis/llm_client.py`

- [x] **6.1.1** 升级 `_STOCK_ANALYSIS_PROMPT`

```python
_STOCK_ANALYSIS_PROMPT_V2 = """你是 Alpha Vault 的 AI 投资分析引擎，请按照以下结构化框架进行分析。

## 标的信息
- 代码: {ticker}
- 名称: {name}
- 市场: {market}

## 技术面数据
{tech_data}

## 基本面数据
{fundamental_data}

## 估值数据
{valuation_data}

## 近期新闻
{news_data}

## 分析框架（必须严格按顺序执行）

### 第一步：快速定性判断
- 行业地位与竞争优势（护城河）
- 管理层质量（从分红/回购/质押行为判断）
- 是否存在价值陷阱信号？（连续亏损/现金流枯竭/资产减值/关联交易异常）

### 第二步：财务质量评估
- ROE 趋势（改善/稳定/恶化）
- 利润含金量（经营现金流 / 净利润 是否 > 0.8）
- 负债结构（有息负债率，短期偿债能力）
- 非经常性损益占比（是否靠补贴/资产处置美化利润）

### 第三步：估值判断
- 当前估值水平 vs 历史区间
- 穿透回报率（Owner Earnings / 市值）是否有吸引力
- 安全边际是否充足（地板价 vs 当前价）

### 第四步：综合结论
- 方向: 看多 / 看空 / 中性
- 置信度: 0-100
- 主要逻辑（3句话以内）
- 关键风险点

## 要求
- 用中文回答，简洁专业
- 控制在 500 字以内
- 如果基本面/估值数据缺失，基于可用数据分析，注明数据不足
"""
```

- [x] **6.1.2** 升级 `llm_analyze_stock` 函数签名

```python
def llm_analyze_stock(
    ticker: str,
    name: str,
    market: str,
    tech_data: dict,
    news_items: list[dict],
    fundamental_data: dict | None = None,    # 新增
    valuation_data: dict | None = None,      # 新增
) -> dict | None:
    """
    升级后的LLM分析:
    - 如果有基本面/估值数据, 使用 V2 prompt (结构化多因子)
    - 如果没有, 降级使用 V1 prompt (现有逻辑, 保持兼容)
    """
```

- [x] **6.1.3** 新增 `_format_fundamental_for_prompt`

```python
def _format_fundamental_for_prompt(data: dict) -> str:
    """把 fundamental.analyze_fundamental() 的结果转成 LLM 可读文本"""
    if not data:
        return "基本面数据暂不可用"
    lines = [
        f"财务质量评分: {data['quality_score']}/100 ({data['quality_label']})",
        f"ROE: {data['profitability']['roe']:.1f}%  毛利率: {data['profitability']['gross_margin']:.1f}%",
        f"近3年营收增长: {data['growth']['revenue_growth_3y']:.1f}%  利润增长: {data['growth']['profit_growth_3y']:.1f}%",
        f"资产负债率: {data['safety']['debt_ratio']:.1f}%  流动比率: {data['safety']['current_ratio']:.2f}",
        f"FCF正年数(近5年): {data['safety']['fcf_positive_years']}  连续分红: {data['safety']['dividend_continuous_years']}年",
        f"PE(TTM): {data['valuation_snapshot']['pe_ttm']:.1f}  PB: {data['valuation_snapshot']['pb']:.2f}",
    ]
    if data.get("risk_flags"):
        lines.append(f"⚠ 风险标记: {', '.join(data['risk_flags'])}")
    return "\n".join(lines)
```

- [x] **6.1.4** 新增 `_format_valuation_for_prompt`

```python
def _format_valuation_for_prompt(data: dict) -> str:
    """把 valuation.valuate() 的结果转成 LLM 可读文本"""
    if not data:
        return "估值数据暂不可用"
    fp = data["floor_price"]
    pr = data["penetration_return"]
    sm = data["safety_margin"]
    lines = [
        f"穿透回报率: {pr['rate']:.1f}% (评级 {pr['grade']})",
        f"地板价均值: {fp['average']:.2f}  当前价: {sm['current_price']:.2f}",
        f"安全边际: {sm['margin_pct']:.1f}% ({sm['verdict']})",
        f"EV/EBITDA: {data['ev_ebitda']['value']:.1f} ({data['ev_ebitda']['percentile']})",
    ]
    return "\n".join(lines)
```

### 6.2 新增烟蒂股专用 Prompt（可选，A股深度分析时使用）

- [x] **6.2.1** 新增 `_CIGBUTT_ANALYSIS_PROMPT`

```python
# 参考烟蒂股分析 Prompt v1.8 的 22 项 Fact Check 清单
# 仅在 deep_analysis + A股 + PB<1.5 时触发

_CIGBUTT_ANALYSIS_PROMPT = """你是一位深度价值投资分析师，请按照烟蒂股分析框架评估该标的。

## 三支柱评估
1. 资产垫: T0(净有息负债/EBITDA) T1(现金-负债/市值) T2(NCAV/市值)
2. 低维护CAPEX: 资本开支/折旧 < 1.2 且资本开支/营收 < 5%
3. 资产变现逻辑: A(分红) B(回购/减资) C(并购/私有化) 是否存在催化剂

## Fact Check (逐项回答 是/否/不确定):
1. 净有息负债/EBITDA < 3?
2. 审计意见为标准无保留?
3. 近3年无重大违规/诉讼?
...（按需裁剪为最关键的10项）

{data}

用中文回答，控制在 600 字以内。
"""
```

---

## 七、Phase 5: 报告结构升级 + 深度分析 API

**目标**：报告卡片增加基本面/估值字段，新增个股深度分析 API。

### 7.1 改造 `analysis/report_generator.py`

- [x] **7.1.1** `_analyze_one` 增加基本面和估值分析

```python
def _analyze_one(ticker, name, market, use_llm=False) -> dict | None:
    # ── 现有: 技术面 + 新闻 ──
    tech = tech_analyze(ticker, market)
    news = fetch_news(ticker, market, limit=8)
    sentiment = analyze_sentiment(news)

    # ── 新增: 基本面 + 估值 (仅非基金标的) ──
    fund_data = None
    val_data = None
    if market != "fund":
        try:
            from analysis.fundamental import analyze_fundamental
            fund_data = analyze_fundamental(ticker, market)
        except Exception as e:
            app_logger.warning(f"[报告] 基本面分析 {ticker} 失败: {e}")
        try:
            from analysis.valuation import valuate
            if fund_data and tech:
                val_data = valuate(ticker, market, fund_data, tech["price"], ...)
        except Exception as e:
            app_logger.warning(f"[报告] 估值分析 {ticker} 失败: {e}")

    # ── 综合置信度升级 ──
    # 现有: confidence = tech_conf + sentiment_score * 15
    # 新增: 基本面质量分 + 估值安全边际 影响置信度
    ...

    # ── LLM 分析升级: 传入基本面+估值数据 ──
    if use_llm:
        llm_result = llm_analyze_stock(ticker, name, market, tech, news,
                                        fundamental_data=fund_data,
                                        valuation_data=val_data)
```

- [x] **7.1.2** 报告卡片新增字段

```python
# 在 item dict 中新增:
item = {
    # ... 现有字段保持不变 ...

    # ── 新增字段 ──
    "fundamentalReason": fund_data["fundamental_summary"] if fund_data else "",
    "valuationReason": val_data["valuation_summary"] if val_data else "",
    "riskFlags": fund_data["risk_flags"] if fund_data else [],
    "qualityScore": fund_data["quality_score"] if fund_data else None,
    "safetyMargin": val_data["safety_margin"]["margin_pct"] if val_data else None,
    "penetrationReturn": val_data["penetration_return"]["rate"] if val_data else None,
}
```

- [x] **7.1.3** 综合置信度公式升级

```python
# 现有公式:
#   confidence = tech_conf + sentiment_score * 15
#
# 升级公式:
#   base = tech_conf                              # 技术面基础分 (30-95)
#   news_mod = sentiment_score * 10               # 新闻情绪修正 (-10 ~ +10)
#   fund_mod = (quality_score - 50) * 0.15        # 基本面修正 (-7.5 ~ +7.5)
#   val_mod = 0
#   if safety_margin > 30: val_mod = +5           # 充足安全边际加分
#   elif safety_margin < 0: val_mod = -5          # 溢价减分
#   confidence = clamp(base + news_mod + fund_mod + val_mod, 20, 95)
```

### 7.2 新增深度分析 API

- [x] **7.2.1** 在 `app.py` 新增 `/api/deep-analysis` 端点

```python
@app.route("/api/deep-analysis", methods=["POST"])
@login_required
def api_deep_analysis():
    """
    个股深度分析 API。
    请求体: {"ticker": "600519", "market": "a_share"}
    返回: 完整的技术面+基本面+估值+LLM综合分析结果
    """
    data = request.get_json(silent=True) or {}
    ticker = data.get("ticker", "").strip()
    market = data.get("market", "").strip()

    if not ticker or not market:
        return jsonify(error="参数不完整"), 400

    try:
        result = _deep_analyze(ticker, market)
        return jsonify(result)
    except Exception as e:
        return jsonify(error=str(e)), 500


def _deep_analyze(ticker: str, market: str) -> dict:
    """执行完整的深度分析"""
    from analysis.technical import analyze as tech_analyze
    from analysis.news_fetcher import fetch_news, analyze_sentiment
    from analysis.fundamental import analyze_fundamental
    from analysis.valuation import valuate
    from analysis.llm_client import llm_analyze_stock, _is_enabled

    tech = tech_analyze(ticker, market)
    news = fetch_news(ticker, market, limit=10)
    sentiment = analyze_sentiment(news)
    fund_data = analyze_fundamental(ticker, market)
    val_data = None
    if fund_data and tech:
        val_data = valuate(ticker, market, fund_data, tech["price"], ...)

    llm_result = None
    if _is_enabled():
        llm_result = llm_analyze_stock(ticker, ..., fund_data, val_data)

    return {
        "ticker": ticker,
        "market": market,
        "technical": tech,
        "news": {"items": news, "sentiment": sentiment},
        "fundamental": fund_data,
        "valuation": val_data,
        "llm_analysis": llm_result,
        "generated_at": datetime.now().isoformat(),
    }
```

### 7.3 models.py 可选扩展

- [x] **7.3.1** 新增 `DeepAnalysisCache` 模型（可选）

```python
class DeepAnalysisCache(db.Model):
    """个股深度分析缓存（避免短时间重复计算）"""
    __tablename__ = "deep_analysis_cache"
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False, index=True)
    market = db.Column(db.String(20), nullable=False)
    data = db.Column(db.Text, nullable=False)           # JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # TTL 由应用层控制，超过 4 小时的缓存视为过期
```

---

## 八、Phase 6: 前端展示 + PDF 年报解析（可选）

### 8.1 前端报告卡片升级

- [x] **8.1.1** `templates/dashboard.html` 增加基本面/估值展示区域

```
报告卡片升级后的布局:
┌──────────────────────────────────┐
│ 股票名称  价格  涨跌幅  置信度    │
├──────────────────────────────────┤
│ 📊 技术面: (现有 techReason)      │
│ 📰 新闻面: (现有 newsReason)      │
│ 📈 基本面: (新增 fundamentalReason)│  ← 新增
│ 💰 估值面: (新增 valuationReason)  │  ← 新增
│ 🤖 AI分析: (现有 llmReason)       │
│ ⚠ 风险: (新增 riskFlags)          │  ← 新增
├──────────────────────────────────┤
│ 入场/止损/止盈  风险回报比         │
│ 安全边际: xx%  穿透回报率: xx%     │  ← 新增
└──────────────────────────────────┘
```

- [x] **8.1.2** 新增深度分析页面 `templates/deep_analysis.html`

```
单股深度分析页面:
- 搜索框输入股票代码
- 点击"深度分析"按钮
- 展示完整的技术面/基本面/估值/LLM分析结果
- 财务指标仪表板 (ROE/毛利率/负债率 趋势图)
- 估值区间图 (当前价 vs 地板价 vs 历史区间)
```

### 8.2 PDF 年报解析（可选，A股增强）

- [x] **8.2.1** 新建 `analysis/pdf_parser.py`

```python
"""
analysis/pdf_parser.py - PDF年报解析器

参考龟龟框架 scripts/pdf_preprocessor.py 的设计:
- 使用 pdfplumber 提取特定章节
- 目标章节: 受限资产、应收账款账龄、关联交易、或有事项、非经常性损益、经营分析、子公司

输入: PDF文件路径
输出: 结构化JSON (各章节文本)

使用场景: 用户上传年报PDF → 提取关键信息 → 喂给 LLM 做深度分析
"""

SECTION_KEYWORDS = {
    "restricted_assets": ["受限资产", "使用受到限制", "受到限制的资产"],
    "ar_aging": ["账龄分析", "应收账款账龄", "按账龄列示"],
    "related_party": ["关联方交易", "关联交易", "关联方关系"],
    "contingent": ["或有事项", "未决诉讼", "担保事项"],
    "non_recurring": ["非经常性损益", "非经常性损益明细"],
    "mda": ["经营情况讨论与分析", "管理层讨论与分析", "董事会报告"],
    "subsidiaries": ["主要子公司", "纳入合并范围", "子公司情况"],
}

def parse_annual_report(pdf_path: str) -> dict: ...
```

- [x] **8.2.2** 在 `app.py` 新增 PDF 上传端点

```python
@app.route("/api/upload-report", methods=["POST"])
@login_required
def api_upload_report():
    """上传年报PDF，提取关键信息"""
    # file = request.files["pdf"]
    # 保存 → parse → 返回结构化数据
    ...
```

- [x] **8.2.3** requirements.txt 新增

```
pdfplumber>=0.10.0
```

---

## 九、实施检查清单

### Phase 1: 基本面数据层
- [x] 3.1.1 创建 `data/financial.py` 基础结构
- [x] 3.1.2 A股财报获取 (`akshare`)
- [x] 3.1.3 美股财报获取 (`yfinance`)
- [x] 3.1.4 港股财报获取
- [x] 3.1.5 Parquet 磁盘缓存
- [x] 3.2.1 创建 `analysis/fundamental.py`
- [x] 3.2.2 财务质量评分逻辑
- [x] 3.2.3 `fundamental_summary` 人话总结
- [x] 3.3.1 `config.yaml` 新增基本面配置
- [x] 3.4.1 `requirements.txt` 新增依赖

### Phase 2: 估值引擎
- [x] 4.1.1 创建 `analysis/valuation.py`
- [x] 4.1.2 地板价计算 (5种方法)
- [x] 4.1.3 穿透回报率计算
- [x] 4.1.4 安全边际计算
- [x] 4.1.5 烟蒂股资产垫分析 (可选)

### Phase 3: 筛选器升级
- [x] 5.1.1 `screen_market` 新增模式参数
- [x] 5.1.2 基本面 Tier 1 粗筛
- [x] 5.1.3 基本面 Tier 2 精筛
- [x] 5.1.4 筛选参数改为从 config.yaml 读取
- [x] 5.2.1 `config.yaml` 新增基本面筛选配置

### Phase 4: LLM Prompt 增强
- [x] 6.1.1 升级 `_STOCK_ANALYSIS_PROMPT` 为 V2
- [x] 6.1.2 升级 `llm_analyze_stock` 函数签名
- [x] 6.1.3 新增 `_format_fundamental_for_prompt`
- [x] 6.1.4 新增 `_format_valuation_for_prompt`
- [x] 6.2.1 烟蒂股专用 Prompt (可选)

### Phase 5: 报告结构升级 + 深度分析 API
- [x] 7.1.1 `_analyze_one` 增加基本面和估值
- [x] 7.1.2 报告卡片新增字段
- [x] 7.1.3 综合置信度公式升级
- [x] 7.2.1 新增 `/api/deep-analysis` 端点
- [x] 7.3.1 `DeepAnalysisCache` 模型 (可选)

### Phase 6: 前端 + PDF (可选)
- [x] 8.1.1 报告卡片 UI 升级
- [x] 8.1.2 深度分析页面
- [x] 8.2.1 PDF 年报解析器
- [x] 8.2.2 PDF 上传端点
- [x] 8.2.3 pdfplumber 依赖

---

## 十、文件变更清单

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| **新建** | `data/financial.py` | 财务报表数据获取层 |
| **新建** | `data/cache/` | Parquet 缓存目录 |
| **新建** | `analysis/fundamental.py` | 基本面分析引擎 |
| **新建** | `analysis/valuation.py` | 估值引擎 |
| **新建** | `analysis/pdf_parser.py` | PDF年报解析 (可选) |
| **新建** | `templates/deep_analysis.html` | 深度分析页面 (可选) |
| **修改** | `analysis/stock_screener.py` | 新增基本面筛选模式 |
| **修改** | `analysis/llm_client.py` | Prompt升级 + 函数签名扩展 |
| **修改** | `analysis/report_generator.py` | 集成基本面+估值 + 新字段 |
| **修改** | `app.py` | 新增 `/api/deep-analysis` 端点 |
| **修改** | `config.yaml` | 新增 fundamental + screener 扩展配置 |
| **修改** | `requirements.txt` | 新增 pyarrow, tushare, pdfplumber |
| **修改** | `models.py` | 新增 DeepAnalysisCache (可选) |
| **修改** | `templates/dashboard.html` | 报告卡片增加基本面/估值展示 |

---

## 十一、知识来源参考

| 来源 | URL | 贡献 |
|------|-----|------|
| 烟蒂股分析 Prompt v1.8 | `terancejiang.github.io/Stock_Analyze_Prompts/` | 资产垫体系、22项Fact Check、买卖规则 |
| 龟龟投资策略 v0.15 | 同上 | 四因子模型、穿透回报率、多Agent架构 |
| Turtle Investment Framework v1.0 | `github.com/terancejiang/Turtle_investment_framework` | `screener_core.py`(两层筛选)、`tushare_collector.py`(财报采集)、`pdf_preprocessor.py`(PDF解析) |

---

## 十二、注意事项

1. **向后兼容**：所有新增功能设计为可选（`fundamental.enabled: true/false`），不影响现有技术面分析流程。基本面/估值数据缺失时，系统降级到现有逻辑。

2. **API 频率控制**：akshare 财报接口频率限制较松但仍需注意；tushare Pro 有每分钟调用限制（200次/分）。通过 Parquet 缓存（24h TTL）大幅减少调用。

3. **数据源选择**：
   - 免费方案：akshare（A股财报质量尚可）+ yfinance（美股）
   - 进阶方案：tushare Pro（A股数据最全，需注册获取 token，基础版免费）
   - 建议先用 akshare 快速落地，后续按需切换 tushare

4. **LLM Token 消耗**：V2 prompt 比 V1 长约 2-3 倍，max_tokens 建议从 2048 调到 3072。如果用本地模型（Ollama/vLLM），影响不大；如果用 ChatGPT/DeepSeek API，需关注成本。

5. **Phase 顺序**：Phase 1 → 2 → 4 → 5 有严格依赖关系；Phase 3 依赖 Phase 1 但可与 Phase 2 并行；Phase 6 依赖 Phase 5 但优先级最低。


---

## Phase 7-11: 体验优化 & 功能丰富 (v2.0 规划)

---

## 十三、Phase 7: 交互体验提升 [P0]

**目标**：提升核心操作路径的流畅度，让用户"进来就能用、一键就到位"。

### 7.1 自选 → 深度分析一键跳转

- [x] **7.1.1** `templates/dashboard.html` 自选卡片增加"深度分析"按钮

```
自选卡片右侧添加图标按钮:
onclick -> window.location = '/deep-analysis?ticker=XXX&market=YYY'
```

- [x] **7.1.2** `templates/dashboard.html` 报告卡片增加"深度分析"链接

```
在报告卡片的 ticker 标签旁加一个小按钮:
点击 -> 跳转到深度分析页，自动填入代码和市场
```

- [x] **7.1.3** `templates/deep_analysis.html` 支持 URL 参数自动填入

```javascript
const params = new URLSearchParams(window.location.search);
if (params.get('ticker')) {
    document.getElementById('deepTicker').value = params.get('ticker');
    document.getElementById('deepMarket').value = params.get('market') || 'a_share';
    runDeepAnalysis();
}
```

### 7.2 市场大盘概览条

- [x] **7.2.1** `app.py` 新增 `/api/market-overview` 端点

```python
# 返回主要指数行情: 上证/深证/创业板/纳斯达克/标普/恒生
# 使用 akshare stock_zh_index_spot_em 获取 A 股指数
# 使用 yfinance 获取 ^IXIC, ^GSPC, ^HSI
```

- [x] **7.2.2** `templates/dashboard.html` 顶部添加大盘指数横条

```
上证 3245.67 +0.45%  深证 10523.12 -0.21%  创业板 2156 +0.33%
纳斯达克 18234 +1.2%  标普 5432 +0.8%  恒生 21345 -0.3%
```

- [x] **7.2.3** `static/style.css` 大盘概览条样式（滚动/固定两种模式）

### 7.3 分步进度条

- [x] **7.3.1** `app.py` 深度分析接口改为 SSE (Server-Sent Events) 流式返回

```python
# 每完成一步推送一次进度:
# step 1: 获取行情数据...
# step 2: 分析技术面...
# step 3: 分析基本面...
# step 4: 估值分析...
# step 5: AI 研判中...
# step 6: 完成
```

- [x] **7.3.2** `templates/deep_analysis.html` 前端接收 SSE 并渐进式渲染

```
进度条: [========....] 正在分析基本面...
每完成一步，对应板块先行渲染，不用等到全部完成
```

### 7.4 报告卡片展开/收起

- [x] **7.4.1** `templates/dashboard.html` 报告卡片默认收起，只显示摘要

```
默认显示: 代码 + 名称 + 方向 + 置信度 + 一行摘要
点击展开: 完整的交易计划 + 四维分析 + AI 深度
```

- [x] **7.4.2** `static/style.css` 展开/收起动画

---

## 十四、Phase 8: 财务数据可视化 [P1]

**目标**：让数字变成图表，关键趋势一目了然。

### 8.1 引入图表库

- [x] **8.1.1** `templates/base.html` 引入 Chart.js CDN

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
```

### 8.2 深度分析页 — 财务趋势图

- [x] **8.2.1** `app.py` 深度分析返回数据增加多年指标序列

```python
# _run_deep_analysis 中，把 financial_data['indicators'] 的多年数据
# 提取为适合图表的格式:
# "chart_data": {
#     "years": ["2020", "2021", "2022", "2023", "2024"],
#     "roe": [15.2, 16.8, 14.3, 12.1, 13.5],
#     "gross_margin": [45.2, 44.8, 43.1, 42.5, 43.8],
#     ...
# }
```

- [x] **8.2.2** `templates/deep_analysis.html` 基本面板块添加趋势图

```
三行图表:
1. 盈利能力: ROE + 毛利率 双轴折线图
2. 成长性: 营收增速 + 利润增速 柱状图
3. 安全性: 负债率 + 流动比率 折线图
```

- [x] **8.2.3** `templates/deep_analysis.html` 估值板块添加区间图

```
估值区间图:
-----[地板价]=======[当前价]===[高估区]-----
     ^ NCAV    ^ BVPS    ^ 当前    ^ 目标价
```

### 8.3 自选列表 — 迷你 K 线火花图

- [x] **8.3.1** `app.py` `/api/watchlist/quotes` 返回近 20 日收盘价序列

- [x] **8.3.2** `templates/dashboard.html` 自选卡片用 Canvas 绘制 sparkline

---

## 十五、Phase 9: 自选监控告警 [P1]

**目标**：从"被动看报告"升级为"主动推信号"。

### 9.1 告警规则模型

- [x] **9.1.1** `models.py` 新增 `AlertRule` 模型

```python
class AlertRule(db.Model):
    __tablename__ = "alert_rules"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ticker = db.Column(db.String(20), nullable=False)
    market = db.Column(db.String(20), nullable=False)
    rule_type = db.Column(db.String(30), nullable=False)
    # rule_type: "price_below", "price_above", "rsi_oversold",
    #            "rsi_overbought", "pe_below", "volume_surge", "macd_cross"
    threshold = db.Column(db.Float)
    enabled = db.Column(db.Boolean, default=True)
    last_triggered = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

- [x] **9.1.2** `app.py` 告警规则 CRUD API

```
POST   /api/alerts          创建告警规则
GET    /api/alerts          获取用户所有规则
PUT    /api/alerts/<id>     修改规则
DELETE /api/alerts/<id>     删除规则
```

### 9.2 告警检测引擎

- [x] **9.2.1** 新建 `scripts/alert_checker.py`

```python
# check_alerts():
#   遍历所有启用的告警规则
#   检测是否触发条件
#   触发后推送 Telegram 通知
#   更新 last_triggered 时间戳
```

- [x] **9.2.2** `scripts/scheduler.py` 添加告警检测定时任务（每 30 分钟一次）

### 9.3 告警管理 UI

- [x] **9.3.1** `templates/dashboard.html` 自选卡片添加"设置告警"按钮
- [x] **9.3.2** 告警设置弹窗（选择规则类型 + 输入阈值）
- [x] **9.3.3** `templates/settings.html` 添加告警规则列表管理区

---

## 十六、Phase 10: 回测与绩效面板 [P2]

**目标**：用数据证明系统有效性，建立信任。

### 10.1 推荐绩效统计

- [x] **10.1.1** `app.py` 新增 `/api/performance` 端点

```python
# 统计指定时间范围内的推荐绩效:
# total_recommendations, win_rate, avg_return,
# max_win, max_loss, profit_factor,
# daily_stats (按日胜率走势)
```

- [x] **10.1.2** `templates/history.html` 绩效仪表板

```
总推荐 245  |  胜率 62.4%  |  盈亏比 1.85
         [胜率走势折线图]
最近推荐表现:
  V 600519 贵州茅台 +5.2% (3天)
  X TSLA 特斯拉 -3.1% (5天)
  V 0700 腾讯 +2.8% (1天)
```

### 10.2 多股对比

- [x] **10.2.1** `app.py` 新增 `/api/compare` 端点

```python
# 对比 2-4 只股票的基本面/估值/技术面
# 输入: tickers = [{ticker, market}, ...]
# 输出: 各标的指标并排数据
```

- [x] **10.2.2** 新建 `templates/compare.html` 对比页面

```
         | 贵州茅台  | 五粮液   | 泸州老窖
---------+----------+---------+----------
质量评分  |   85     |   72    |   68
ROE      |  28.5%   |  22.1%  |  19.8%
安全边际  |  -15%    |  +12%   |  +25%
穿透回报  |  8.2%    |  10.5%  |  12.1%
技术信号  |  看多    |  中性    |  看多
```

- [x] **10.2.3** `base.html` 导航栏添加"对比"入口

---

## 十七、Phase 11: 周报 & 数据源扩展 [P3]

**目标**：定期复盘 + 拓宽信息面。

### 11.1 周度复盘报告

- [x] **11.1.1** `analysis/report_generator.py` 新增 `generate_weekly_report(market)`

```python
# 汇总本周所有日报推荐的表现:
# 统计: 胜率、平均收益、最佳/最差推荐
# 市场热点变化: 本周 vs 上周情绪对比
# 信号质量评估: 各维度贡献度
```

- [x] **11.1.2** `scripts/scheduler.py` 每周五 18:00 自动生成并推送周报
- [x] **11.1.3** `templates/history.html` 周报展示卡片

### 11.2 数据源扩展

- [x] **11.2.1** `data/announcement.py` 公告/研报摘要采集（可选）

```python
# fetch_announcements(ticker, market, days=30):
#   从东方财富/巨潮资讯获取公告标题列表
#   akshare.stock_notice_report 或爬虫
```

- [x] **11.2.2** `data/fund_flow.py` 资金流向数据（可选）

```python
# get_fund_flow(ticker, market):
#   获取主力/散户资金流向
#   akshare.stock_individual_fund_flow
```

- [x] **11.2.3** 将公告和资金流向数据集成到 LLM Prompt

---

## 十八、Phase 7-11 实施检查清单

### Phase 7: 交互体验提升 [P0]
- [x] 7.1.1 自选卡片"深度分析"按钮
- [x] 7.1.2 报告卡片"深度分析"链接
- [x] 7.1.3 深度分析页 URL 参数自动填入
- [x] 7.2.1 `/api/market-overview` 大盘指数端点
- [x] 7.2.2 仪表盘大盘概览条 UI
- [x] 7.2.3 大盘概览条样式
- [x] 7.3.1 深度分析 SSE 流式接口
- [x] 7.3.2 前端分步进度条渲染
- [x] 7.4.1 报告卡片展开/收起
- [x] 7.4.2 展开/收起动画

### Phase 8: 财务数据可视化 [P1]
- [x] 8.1.1 引入 Chart.js
- [x] 8.2.1 深度分析返回多年指标序列
- [x] 8.2.2 基本面趋势图
- [x] 8.2.3 估值区间图
- [x] 8.3.1 自选行情返回近 20 日价格
- [x] 8.3.2 自选卡片 sparkline

### Phase 9: 自选监控告警 [P1]
- [x] 9.1.1 `AlertRule` 数据模型
- [x] 9.1.2 告警 CRUD API
- [x] 9.2.1 `alert_checker.py` 检测引擎
- [x] 9.2.2 定时任务集成 (30分钟)
- [x] 9.3.1 自选卡片"设置告警"按钮
- [x] 9.3.2 告警设置弹窗
- [x] 9.3.3 设置页告警列表管理

### Phase 10: 回测与绩效面板 [P2]
- [x] 10.1.1 `/api/performance` 绩效统计端点
- [x] 10.1.2 绩效仪表板 UI
- [x] 10.2.1 `/api/compare` 多股对比端点
- [x] 10.2.2 `compare.html` 对比页面
- [x] 10.2.3 导航栏添加"对比"入口

### Phase 11: 周报 & 数据源扩展 [P3]
- [x] 11.1.1 `generate_weekly_report` 周报生成
- [x] 11.1.2 定时任务: 周五 18:00 周报
- [x] 11.1.3 周报展示卡片
- [x] 11.2.1 公告/研报摘要采集 (可选)
- [x] 11.2.2 资金流向数据 (可选)
- [x] 11.2.3 集成到 LLM Prompt

---

## 十九、Phase 7-11 依赖关系

```
Phase 7 (交互体验)   --> 无依赖，可立即开始
Phase 8 (数据可视化)  --> 依赖 Chart.js 引入
Phase 9 (监控告警)    --> 依赖 AlertRule 模型 + scheduler 集成
Phase 10 (回测绩效)   --> 依赖 RecommendationTrack 有足够数据积累
Phase 11 (周报/数据源) --> 依赖 Phase 10 绩效统计 + 新数据源接口

推荐实施顺序: Phase 7 -> Phase 8 -> Phase 9 -> Phase 10 -> Phase 11
其中 Phase 7 的 4 个子模块可以独立并行实施。
```

## 二十、Phase 7-11 文件变更预估

| 操作 | 文件路径 | Phase | 说明 |
|------|----------|-------|------|
| **修改** | `templates/dashboard.html` | 7, 8 | 深度分析跳转、大盘条、卡片收起、sparkline |
| **修改** | `templates/deep_analysis.html` | 7, 8 | URL 参数、SSE 进度条、趋势图 |
| **修改** | `templates/history.html` | 10, 11 | 绩效面板、周报卡片 |
| **修改** | `templates/base.html` | 8, 10 | Chart.js CDN、对比入口 |
| **修改** | `templates/settings.html` | 9 | 告警规则管理 |
| **修改** | `app.py` | 7-11 | 新增 API 端点 |
| **修改** | `models.py` | 9 | AlertRule 模型 |
| **修改** | `static/style.css` | 7-11 | 新组件样式 |
| **修改** | `analysis/report_generator.py` | 11 | 周报生成 |
| **修改** | `scripts/scheduler.py` | 9, 11 | 告警检测、周报定时 |
| **新建** | `templates/compare.html` | 10 | 多股对比页 |
| **新建** | `scripts/alert_checker.py` | 9 | 告警检测引擎 |
| **新建** | `data/announcement.py` | 11 | 公告采集 (可选) |
| **新建** | `data/fund_flow.py` | 11 | 资金流向 (可选) |
