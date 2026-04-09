"""Shared data models - dataclasses for screening, recommendations, etc."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScreeningResult:
    """Single stock screening result."""
    ticker: str
    name: str
    market: str          # us_stock | hk_stock
    score: float
    price: float = 0.0
    change_pct: float = 0.0
    volume: float = 0.0
    market_cap: float = 0.0
    pe_ttm: float | None = None
    pb: float | None = None
    factors: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecommendationItem:
    """Single recommendation entry."""
    ticker: str
    name: str
    market: str
    strategy: str        # short_term | swing
    direction: str       # buy | sell
    score: float = 0.0
    confidence: int = 0
    tech_score: int = 0
    news_score: int = 0
    fundamental_score: int = 0
    combined_score: int = 0

    entry_price: float = 0.0
    entry_2: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    take_profit_2: float = 0.0
    holding_days: int = 5

    tech_reason: str = ""
    news_reason: str = ""
    fundamental_reason: str = ""
    llm_reason: str = ""
    valuation_summary: str = ""

    quality_score: float | None = None
    safety_margin: float | None = None
    risk_flags: list[str] = field(default_factory=list)

    # Options & insider signals
    options_pc_ratio: float | None = None
    options_unusual_activity: bool = False
    insider_signal: str = ""
    insider_net_flow: float = 0.0

    # Macro snapshot
    macro_yield_spread: float | None = None
    macro_risk_level: str = ""

    price: float = 0.0
    change_pct: float = 0.0


@dataclass
class DeepAnalysisResult:
    """Deep analysis output for a single stock."""
    ticker: str
    market: str
    technical: dict[str, Any] | None = None
    news: dict[str, Any] | None = None
    fundamental: dict[str, Any] | None = None
    valuation: dict[str, Any] | None = None
    llm_analysis: str | None = None
    chart_data: dict[str, Any] | None = None
    generated_at: str = ""
