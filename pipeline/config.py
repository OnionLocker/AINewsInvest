"""Pipeline configuration - dataclass models loaded from config.yaml.

Every parameter carries a sensible default so the system works even
without the YAML sections.  Inspired by astock-quant/pipeline/config.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ScreeningConfig:
    """Pre-screening thresholds and ranking weights."""
    min_market_cap: float = 1.0e9
    min_avg_volume: int = 500_000
    min_dollar_volume: float = 1.0e8  # $100M snapshot (Stage A fast filter)
    min_avg_dollar_volume_20d: float = 2.0e8  # $200M 20-day avg (Stage B precise)
    min_turnover_ratio: float = 0.003  # 0.3% daily turnover
    max_pe: float = 80.0
    min_pe: float = 0
    max_pb: float = 15.0
    max_daily_change_pct: float = 10.0
    # v5: 5-factor model weights (must sum to 1.0)
    weight_acceleration: float = 0.25
    weight_volume_anomaly: float = 0.20
    weight_trend_setup: float = 0.30
    weight_volatility_fit: float = 0.10
    weight_fundamental: float = 0.15
    # Absolute quality gate
    min_absolute_score: float = 35.0
    # Volatility fit — strategy-aware optimal range
    optimal_vol_short: float = 0.025
    optimal_vol_swing: float = 0.018
    optimal_vol_width: float = 0.025
    # Legacy compat (still read from config.yaml if present)
    weight_momentum: float = 0.35
    weight_trend: float = 0.25
    weight_quality: float = 0.20
    weight_volatility: float = 0.20


@dataclass
class SynthesisConfig:
    """Score synthesis weights and thresholds."""
    news_weight: float = 0.15
    tech_weight: float = 0.55
    fundamental_weight: float = 0.30
    min_confidence: int = 55
    quality_threshold: int = 50
    adaptive_threshold_drop: int = 20
    adaptive_threshold_floor: int = 30
    cross_fill_factor: float = 0.3
    # v7: Quality tier boundaries (conviction_score)
    high_min_conviction: float = 42.0
    medium_min_conviction: float = 28.0
    low_min_conviction: float = 15.0
    # v7: Top-N output per regime
    top_n_normal: int = 5
    top_n_cautious: int = 5
    top_n_bearish: int = 3


@dataclass
class ShortTermConfig:
    """Short-term strategy parameters."""
    max_recommendations: int = 5
    news_weight: float = 0.40
    tech_weight: float = 0.55
    fundamental_weight: float = 0.05
    default_stop_loss_pct: float = 0.97
    default_take_profit_pct: float = 1.05
    take_profit_2_pct: float = 1.08
    atr_sl_multiplier: float = 2.0
    atr_tp_multiplier: float = 3.0
    default_holding_days: int = 3
    max_holding_days: int = 5
    # Trailing stop & per-strategy SL bounds (v4.1)
    trailing_activation_pct: float = 0.50
    trailing_distance_pct: float = 0.40
    sl_max_pct: float = 0.06
    sl_min_pct: float = 0.015


@dataclass
class SwingConfig:
    """Swing / medium-term strategy parameters."""
    max_recommendations: int = 5
    news_weight: float = 0.40
    tech_weight: float = 0.35
    fundamental_weight: float = 0.25
    default_stop_loss_pct: float = 0.94
    default_take_profit_pct: float = 1.12
    take_profit_2_pct: float = 1.20
    atr_sl_multiplier: float = 2.0
    atr_tp_multiplier: float = 3.5
    default_holding_days: int = 10
    max_holding_days: int = 30
    # Trailing stop & per-strategy SL bounds (v4.1)
    trailing_activation_pct: float = 0.40
    trailing_distance_pct: float = 0.35
    sl_max_pct: float = 0.10
    sl_min_pct: float = 0.015
    # v7: Top-N output per regime
    top_n_normal: int = 3
    top_n_cautious: int = 3
    top_n_bearish: int = 2


@dataclass
class WinRateConfig:
    """Win-rate tracking and cleanup settings."""
    short_retention_days: int = 21
    swing_retention_days: int = 90
    evaluation_retention_days: int = 21
    enable_auto_cleanup: bool = True


@dataclass
class NewsSourceConfig:
    """Multi-source news aggregation settings."""
    finnhub_key: str = ""
    marketaux_key: str = ""
    max_per_source: int = 10
    max_total: int = 15


@dataclass
class LLMConfig:
    """LLM connection parameters."""
    enabled: bool = False
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    temperature: float = 0.3
    max_tokens: int = 2048
    timeout: int = 60


@dataclass
class FallbackConfig:
    """Deterministic fallback scores when LLM Agent fails."""
    base_score: int = 50
    ma_bullish_bonus: int = 12
    ma_short_golden_bonus: int = 5
    ma_bearish_penalty: int = 10
    volume_ratio_strong: float = 1.5
    volume_strong_bonus: int = 8
    volume_ratio_medium: float = 1.0
    volume_medium_bonus: int = 3
    entry_discount: float = 0.995
    entry_2_discount: float = 0.99
    stop_loss_pct: float = 0.95
    take_profit_pct: float = 1.08
    holding_days: int = 3
    agent_version: str = "fallback-v1"


@dataclass
class AgentConfig:
    """LLM Agent orchestration settings."""
    enabled: bool = False
    news_version: str = "news-sentiment-v1"
    tech_version: str = "technical-v1"
    max_retries: int = 1
    batch_size: int = 20
    fallback: FallbackConfig = field(default_factory=FallbackConfig)


@dataclass
class SchedulerConfig:
    """Built-in pipeline scheduler settings."""
    enabled: bool = False
    us_run_time: str = "07:30"
    hk_run_time: str = "07:30"


@dataclass
class MarketInfo:
    """Per-market metadata."""
    currency: str = "USD"
    currency_symbol: str = "$"
    timezone: str = "America/New_York"
    trading_hours: str = "09:30-16:00"


@dataclass
class IndexEntry:
    """A single index for the stock pool."""
    index: str = ""
    name: str = ""


@dataclass
class PipelineConfig:
    """Top-level configuration aggregating all sub-configs.

    Usage::

        cfg = PipelineConfig.load()
        cfg.screening.min_market_cap   # 1e9
        cfg.llm.enabled                # False
    """
    max_candidates: int = 40
    max_recommendations: int = 20

    screening: ScreeningConfig = field(default_factory=ScreeningConfig)
    synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)
    short_term: ShortTermConfig = field(default_factory=ShortTermConfig)
    swing: SwingConfig = field(default_factory=SwingConfig)
    win_rate: WinRateConfig = field(default_factory=WinRateConfig)
    news: NewsSourceConfig = field(default_factory=NewsSourceConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    markets: dict[str, MarketInfo] = field(default_factory=dict)
    stock_pool: dict[str, list[IndexEntry]] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> PipelineConfig:
        if config_path is None:
            config_path = Path(os.environ.get(
                "ALPHAVAULT_CONFIG",
                Path(__file__).resolve().parent.parent / "config.yaml",
            ))
        config_path = Path(config_path)
        raw: dict[str, Any] = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}

        pipe = raw.get("pipeline", {}) or {}
        llm_raw = raw.get("llm", {}) or {}
        news_raw = raw.get("news_sources", {}) or {}
        mkt_raw = raw.get("market", {}) or {}
        pool_raw = raw.get("stock_pool", {}) or {}
        agent_raw = raw.get("agent", {}) or {}
        sched_raw = raw.get("scheduler", {}) or {}

        markets = {}
        for key, val in mkt_raw.items():
            if isinstance(val, dict):
                markets[key] = _load_dc(MarketInfo, val)

        stock_pool: dict[str, list[IndexEntry]] = {}
        for key, entries in pool_raw.items():
            if isinstance(entries, list):
                stock_pool[key] = [
                    IndexEntry(index=e.get("index", ""), name=e.get("name", ""))
                    for e in entries if isinstance(e, dict)
                ]

        agent_cfg = _load_dc(AgentConfig, agent_raw)
        fallback_raw = agent_raw.get("fallback", {})
        if fallback_raw:
            agent_cfg.fallback = _load_dc(FallbackConfig, fallback_raw)

        return cls(
            max_candidates=int(pipe.get("max_candidates", cls.max_candidates)),
            max_recommendations=int(pipe.get("max_recommendations", cls.max_recommendations)),
            screening=_load_dc(ScreeningConfig, pipe.get("screening", {})),
            synthesis=_load_dc(SynthesisConfig, pipe.get("synthesis", {})),
            short_term=_load_dc(ShortTermConfig, pipe.get("short_term", {})),
            swing=_load_dc(SwingConfig, pipe.get("swing", {})),
            win_rate=_load_dc(WinRateConfig, pipe.get("win_rate", {})),
            news=_load_dc(NewsSourceConfig, news_raw),
            llm=_load_dc(LLMConfig, llm_raw),
            agent=agent_cfg,
            scheduler=_load_dc(SchedulerConfig, sched_raw),
            markets=markets,
            stock_pool=stock_pool,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce(field_type: type, value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, field_type):
        return value
    try:
        if field_type is float:
            return float(value)
        if field_type is int:
            return int(float(value))
        if field_type is str:
            return str(value)
        if field_type is bool:
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)
    except (TypeError, ValueError):
        pass
    return value


def _load_dc(cls: type, data: dict | None):
    if not data:
        return cls()
    fields_map = {f.name: f for f in cls.__dataclass_fields__.values()}
    kwargs: dict[str, Any] = {}
    for k, v in data.items():
        if k not in fields_map:
            continue
        ft = fields_map[k].type
        if isinstance(ft, str):
            ft = {"float": float, "int": int, "str": str, "bool": bool}.get(ft, type(v))
        kwargs[k] = _coerce(ft, v)
    return cls(**kwargs)


# Singleton
_cached: PipelineConfig | None = None


def get_config(force_reload: bool = False) -> PipelineConfig:
    """Module-level cached config singleton."""
    global _cached
    if _cached is None or force_reload:
        _cached = PipelineConfig.load()
    return _cached
