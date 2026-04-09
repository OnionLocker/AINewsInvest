# Alpha Vault v7 Pipeline Flow

```
 ╔═══════════════════════════════════════════════════════════════════════════╗
 ║                   TRIGGER (scheduler / CLI)                              ║
 ║  US: 07:30 ET (19:30 Beijing)    HK: 07:30 HKT (if enabled)            ║
 ║  python main.py run --market us_stock [--force]                         ║
 ╚═══════════════════════════════════════════════════════════════╦═══════════╝
                                                                ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                     PRE-FLIGHT: MARKET REGIME                           │
 │                                                                         │
 │  SPY/VIX/yield curve → regime level:                                    │
 │    normal    1d > -2%, VIX < 25                                         │
 │    cautious  VIX 25-35 or yield inversion                               │
 │    bearish   1d -2~-3% or 5d -3~-5% or VIX > 35                        │
 │    crisis    1d < -3% or 5d < -5%                                       │
 │                                                                         │
 │  crisis → US: 0 recs (pipeline still runs for logging)                  │
 │           HK: skip entire pipeline                                      │
 └──────────────────────────────────────────────────────────────────────────┘
                                    │
 ═══════════════════════════════════╪═══════════════════════════════════════
  LAYER 1: QUANTITATIVE SCREENING  │  ~20 sec
 ═══════════════════════════════════╪═══════════════════════════════════════
                                    ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  STOCK POOL                                                        │
 │  US: S&P 500 (~500) + Nasdaq 100 (~100) → deduplicated ~570       │
 │  HK: HSI (~80) + HSTECH (~30) → deduplicated ~100                 │
 │  Source: Wikipedia (cached in data/stock_pool.json)                │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  STAGE A: HARD FILTER + PRE-RANK                   ~570 → ~180    │
 │                                                                     │
 │  Hard gates (any fail = reject):                                    │
 │    ├─ market cap ≥ $1B          (cfg: min_market_cap)               │
 │    ├─ avg volume ≥ 500K shares  (cfg: min_avg_volume)               │
 │    └─ |daily change| ≤ 10%     (cfg: max_daily_change_pct)         │
 │                                                                     │
 │  Pre-rank: 52-week position bell curve                              │
 │    sweet zone 40-70% from low → highest rank                        │
 │    0% (beaten) or 100% (overextended) → lowest rank                 │
 │                                                                     │
 │  Output: top max(top_n×3, 80) = top 180                            │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  STAGE B: FINANCIAL DATA + QUALITY GATE             ~180 → ~120   │
 │                                                                     │
 │  Fetch: ROE, revenue growth, FCF, debt ratio, margins, PEG...      │
 │                                                                     │
 │  Quality gate (reject if ALL three):                                │
 │    ├─ ROE < -10%                                                    │
 │    ├─ FCF < 0                                                       │
 │    └─ Revenue growth < -10%                                         │
 │  Also reject: PB > 15                                               │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  STAGE C: TREND FILTER + 5-FACTOR RANKING           ~120 → ~60    │
 │                                                                     │
 │  Trend reject: price < MA20 < MA50 AND price < MA50×0.90           │
 │  (confirmed deep downtrend only)                                    │
 │                                                                     │
 │  5-Factor Model (normalized [0,1], weighted sum):                   │
 │  ┌────────────────────────┬────────┬──────────────────────────────┐ │
 │  │ Factor                 │ Weight │ What it measures             │ │
 │  ├────────────────────────┼────────┼──────────────────────────────┤ │
 │  │ Trend Setup            │  30%   │ MA alignment + pullback      │ │
 │  │ Acceleration           │  25%   │ Momentum increasing?         │ │
 │  │ Volume Anomaly         │  20%   │ Recent volume surge          │ │
 │  │ Fundamental             │  15%   │ ROE, growth, FCF, PEG       │ │
 │  │ Volatility Fit         │  10%   │ Optimal 1.5-2.5% daily vol  │ │
 │  └────────────────────────┴────────┴──────────────────────────────┘ │
 │                                                                     │
 │  Absolute quality gate: score ≥ 35 (cfg: min_absolute_score)       │
 │  Sector diversification: max 20 per sector (top_n/3)               │
 │                                                                     │
 │  Output: top 60 candidates (cfg: max_candidates = 60)              │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       │
 ═══════════════════════════════════════════════════════╪═══════════════
  LAYER 2: TECHNICAL DATA ENRICHMENT                   │  ~15 sec
 ═══════════════════════════════════════════════════════╪═══════════════
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  ENRICHMENT (parallel fetch)                        60 → 60       │
 │                                                                     │
 │  Per candidate, compute/fetch:                                      │
 │    ├─ K-line 80 days (cached from L1)                              │
 │    ├─ MA5, MA10, MA20, MA60                                        │
 │    ├─ ATR 20d (for SL/TP sizing)                                   │
 │    ├─ RSI 14, MACD, Bollinger Bands, OBV                          │
 │    ├─ Volume profile → support/resistance levels                   │
 │    ├─ Weekly trend (4w vs 8w MA)                                   │
 │    ├─ Volatility class (high/medium/low)                           │
 │    ├─ Binary signals: ma_bullish, volume_expansion, near_support.. │
 │    ├─ Earnings proximity (next 5 trading days)                     │
 │    ├─ Insider trading activity (buy/sell patterns)                 │
 │    └─ Options signal (P/C ratio, unusual activity)                 │
 │                                                                     │
 │  fundamental_score computed (0-100, base 50)                       │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       │
 ═══════════════════════════════════════════════════════╪═══════════════
  LAYER 3: NEWS SENTIMENT AGENT                        │  ~40 sec
 ═══════════════════════════════════════════════════════╪═══════════════
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  NewsSkill (LLM, batched ×10)                       60 → ~25      │
 │                                                                     │
 │  Input per stock:                                                   │
 │    12 recent news items + market context + macro data               │
 │                                                                     │
 │  LLM → catalysts, risks, event flags, sector sentiment             │
 │                                                                     │
 │  Deterministic post-processing:                                     │
 │    base 50 + catalyst impact (±24 ea) + risk severity (−15 ea)    │
 │    + event flags (FDA +10, guidance ±8, insider −4)                │
 │    + sector sentiment (±3) + regime adjustment (±5)                │
 │    → news_score [0, 100]   action: buy/hold/avoid                  │
 │                                                                     │
 │  News filter: top 15-20 by news_score                              │
 │  Tech bypass: +5 stocks with strong technicals but low news        │
 │    (ma_bullish + volume_expansion + !overbought + !divergence)     │
 │                                                                     │
 │  Output: ~20-25 candidates with news_score + action                │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       │
 ═══════════════════════════════════════════════════════╪═══════════════
  LAYER 4: TECHNICAL ANALYSIS AGENT                    │  ~60 sec
 ═══════════════════════════════════════════════════════╪═══════════════
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  TechSkill (Hybrid: deterministic + LLM)            ~25 → ~25     │
 │                                                                     │
 │  STEP 1: Deterministic score for ALL candidates                    │
 │    base 50, regime-aware multipliers                                │
 │    + MA alignment (±12)                                             │
 │    + volume ratio continuous (−4 to +10)                           │
 │    + overbought penalty (0 to −20)                                 │
 │    + RSI 14-period (−12 to +10)                                    │
 │    + Bollinger position (−7 to +6)                                 │
 │    + MACD histogram (−5 to +5)                                     │
 │    + OBV trend (±3)                                                │
 │    + weekly trend (−8 to +3)                                       │
 │    + volatility penalty (−10 to +2)                                │
 │    + divergence penalty (−12)                                      │
 │    → deterministic tech_score [0, 100]                             │
 │                                                                     │
 │  STEP 2: LLM call for BORDERLINE (40-65) and HIGH (>70) only      │
 │    LLM → pattern recognition, setup quality, trend assessment      │
 │    Hybrid blend: 60% deterministic + 40% LLM pattern               │
 │    Setup quality clamps: avoid→max 45, excellent→min 55            │
 │                                                                     │
 │  STEP 3: Consistency check                                          │
 │    action outside expected score range → blend 60/40 with midpoint │
 │                                                                     │
 │  Output: tech_score [0, 100] + action for all candidates           │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       │
 ═══════════════════════════════════════════════════════╪═══════════════
  LAYER 5: SYNTHESIS + QUALITY TIERS (v7)              │  ~10 sec
 ═══════════════════════════════════════════════════════╪═══════════════
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  CROSS-FILL: Missing signal → diluted estimate + confidence penalty│
 │    no news → news_score = 50 + (tech-50)×0.3, confidence −12      │
 │    no tech → tech_score = 50 + (news-50)×0.3, confidence −15      │
 ├─────────────────────────────────────────────────────────────────────┤
 │  CONFIDENCE (multi-factor, base 50):                               │
 │    direction agreement ±28  (both buy=+28, contradiction=−28)      │
 │    score convergence   ±18  (gap 0→+15, gap 50→−18)               │
 │    fundamental align   ±8   (mismatch penalty)                      │
 │    strength alignment  ±8   (both >70→+8)                          │
 │    risk flags          −18  (8+ flags→−18)                         │
 │    insider signal      ±15  (strong_buy→+12, strong_sell→−15)      │
 │    source quality      ±5   (LLM→+3, fallback→−2)                 │
 │    → confidence [10, 95]                                            │
 ├─────────────────────────────────────────────────────────────────────┤
 │  COMBINED SCORE:                                                    │
 │    = (news×0.15 + tech×0.55 + fund×0.30) / 1.0                    │
 │    (weights: short_term default, adaptive adjustment if data)       │
 │    + insider selling penalty (strong_sell → −15)                   │
 │    → combined_score [0, 100]                                        │
 ├─────────────────────────────────────────────────────────────────────┤
 │  CONVICTION SCORE:                                                  │
 │    = combined × (confidence / 100) ^ 0.7                            │
 │    Exponent 0.7: confidence matters but doesn't dominate            │
 ├─────────────────────────────────────────────────────────────────────┤
 │                                                                     │
 │  v7 QUALITY TIER (replaces v6 dual hard-filter):                   │
 │                                                                     │
 │    conviction ≥ 42 ──→  HIGH     full trade params shown           │
 │                         ┃        green badge "高信心"               │
 │    conviction ≥ 28 ──→  MEDIUM   trade params + caution banner     │
 │                         ┃        blue badge "中等"                  │
 │    conviction ≥ 15 ──→  LOW      NO trade params (watch-only)      │
 │                         ┃        orange badge "观望"                │
 │    conviction < 15 ──→  EXCLUDED not shown at all                   │
 │                                                                     │
 │  R:R rejected → forced to LOW (watch-only)                         │
 │                                                                     │
 │  Regime top-N:                                                      │
 │    crisis   → 0 (sit out)                                          │
 │    bearish  → top 3, HIGH tier only                                │
 │    cautious → top 5                                                │
 │    normal   → top 5                                                │
 │                                                                     │
 │  Post-filter:                                                       │
 │    sector concentration ≤ 40%                                      │
 │    pairwise correlation ≤ 0.7 (drop lower-ranked duplicate)        │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       │
 ═══════════════════════════════════════════════════════╪═══════════════
  LAYER 6: TRADE PARAMETERS (code-only, no LLM)       │  ~5 sec
 ═══════════════════════════════════════════════════════╪═══════════════
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  For each HIGH / MEDIUM tier recommendation:                       │
 │                                                                     │
 │  ENTRY:                                                             │
 │    breakout (broke 20d high + vol expansion):                      │
 │      entry = price × 1.002 (chase)                                 │
 │    pullback:                                                        │
 │      entry = support × 1.01 or MA20 × 1.005 (limit order)         │
 │    entry_2 = entry × 0.985 (backup fill)                           │
 │                                                                     │
 │  STOP LOSS (ATR-based, bounded):                                   │
 │    SL = entry − ATR × 2.0 (atr_sl_multiplier)                     │
 │    breakout: SL = entry − ATR × 1.34 (tighter)                    │
 │    bounds: [entry × 0.94, entry × 0.985] (1.5% ~ 6%)              │
 │                                                                     │
 │  TAKE PROFIT (ATR-based):                                          │
 │    TP = entry + ATR × 3.0 (atr_tp_multiplier)                     │
 │    or resistance × 0.99 (natural target)                           │
 │    TP2 = resistance_2 or entry × 1.08                              │
 │    TP3 = entry + ATR × 3 or TP2 × 1.04                            │
 │    minimum: TP ≥ entry × 1.025                                     │
 │                                                                     │
 │  R:R CHECK (hard rule):                                             │
 │    reward / risk ≥ 1.5 → OK, show params                          │
 │    reward / risk < 1.5 → mark watch-only (no trade params)        │
 │                                                                     │
 │  TRAILING STOP:                                                     │
 │    activate at 50% of TP distance                                  │
 │    trail by 40% of activation distance                             │
 │                                                                     │
 │  HOLDING: 3 days (short_term), 10 days (swing)                    │
 │  POSITION: 2-10% of portfolio (score/conf/vol/regime adjusted)     │
 └─────────────────────────────────────────────────────┬───────────────┘
                                                       │
 ═══════════════════════════════════════════════════════╪═══════════════
  OUTPUT & STORAGE                                     │
 ═══════════════════════════════════════════════════════╪═══════════════
                                                       ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  SAVE & PUBLISH                                                     │
 │                                                                     │
 │  system.db:                                                         │
 │    daily_recommendation_runs     (admin internal)                   │
 │    daily_recommendation_items    (per stock detail)                 │
 │    published_recommendation_runs (user-facing)                      │
 │    published_recommendation_items                                   │
 │    win_rate_records (only HIGH/MEDIUM with trade params)            │
 │                                                                     │
 │  API → Frontend:                                                    │
 │    GET /api/recommendations/{market}/today                         │
 │    Sorted by conviction_score DESC                                  │
 │                                                                     │
 │  Frontend display:                                                  │
 │    推荐列表 5 只 (2 高信心 / 2 中等 / 1 观望)                      │
 │    ┌──────────────────────────────────┐                             │
 │    │ NVDA  [高信心]  Technology       │                             │
 │    │ $875 ↑2.3%  →买入  置信度 82%   │                             │
 │    │ Entry $873  SL $865  TP $899    │                             │
 │    ├──────────────────────────────────┤                             │
 │    │ AAPL  [中等]    Technology       │                             │
 │    │ $198 ↑1.1%  →买入  置信度 58%   │                             │
 │    │ ⚠ 信号中等强度 - 控制仓位      │                             │
 │    ├──────────────────────────────────┤                             │
 │    │ META  [观望]    Communication    │                             │
 │    │ $520 ↑0.8%  →买入  置信度 35%   │                             │
 │    │ 仅供参考 - 暂不提供交易参数     │                             │
 │    └──────────────────────────────────┘                             │
 └─────────────────────────────────────────────────────────────────────┘


 ═══════════════════════════════════════════════════════════════════════
  CANDIDATE COUNT SUMMARY
 ═══════════════════════════════════════════════════════════════════════

  Stock Pool          ~570    S&P 500 + Nasdaq 100 (deduplicated)
      ↓ Stage A       ~180    hard gates + 52-week pre-rank
      ↓ Stage B       ~120    financial quality gate
      ↓ Trend+Score    ~60    trend filter + 5-factor ≥ 35 + sector cap
  ─── Layer 1 out ──── 60    cfg.max_candidates
      ↓ Enrichment     60    + technical indicators + earnings/insider/options
  ─── Layer 2 out ──── 60
      ↓ News Agent    ~25    top by news_score + tech bypass
  ─── Layer 3 out ─── ~25
      ↓ Tech Agent    ~25    deterministic + LLM hybrid scoring
  ─── Layer 4 out ─── ~25
      ↓ Synthesis       5    quality tier + regime cap + sector/corr filter
  ─── Layer 5 out ───── 5    (3-5 depending on regime)
      ↓ Trade params    5    entry/SL/TP for HIGH+MEDIUM; watch-only for LOW
  ─── Layer 6 out ───── 5    FINAL OUTPUT
                              (normal: 5, bearish: 0-3, crisis: 0)

  Total time: ~2.5 minutes per market
```
