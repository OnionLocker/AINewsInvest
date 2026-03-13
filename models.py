"""
models.py - SQLAlchemy 数据模型

User               → 用户账号 + Telegram 加密配置
Watchlist          → 用户自选标的
DailyReport        → 每日 AI 投研报告
RecommendationTrack → 推荐准确率追踪
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    tg_bot_token_enc = db.Column(db.Text, default="")
    tg_chat_id_enc = db.Column(db.Text, default="")

    watchlist = db.relationship("Watchlist", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def set_tg_config(self, bot_token: str, chat_id: str):
        from utils.crypto import encrypt
        self.tg_bot_token_enc = encrypt(bot_token) if bot_token else ""
        self.tg_chat_id_enc = encrypt(chat_id) if chat_id else ""

    def get_tg_config(self) -> tuple[str, str]:
        from utils.crypto import decrypt
        token = decrypt(self.tg_bot_token_enc) if self.tg_bot_token_enc else ""
        chat_id = decrypt(self.tg_chat_id_enc) if self.tg_chat_id_enc else ""
        return token, chat_id

    @property
    def tg_configured(self) -> bool:
        return bool(self.tg_bot_token_enc and self.tg_chat_id_enc)


class Watchlist(db.Model):
    """用户自选股/基金"""
    __tablename__ = "watchlist"
    __table_args__ = (db.UniqueConstraint("user_id", "ticker", "market", name="uq_user_ticker"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    ticker = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    market = db.Column(db.String(20), nullable=False)  # a_share / us_stock / hk_stock / fund
    added_at = db.Column(db.DateTime, default=datetime.utcnow)


class DailyReport(db.Model):
    """每日 AI 投研报告（按市场+日期存储）"""
    __tablename__ = "daily_reports"
    __table_args__ = (db.UniqueConstraint("market", "report_date", name="uq_market_date"),)

    id = db.Column(db.Integer, primary_key=True)
    market = db.Column(db.String(20), nullable=False, index=True)
    report_date = db.Column(db.Date, nullable=False, default=date.today)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    data = db.Column(db.Text, nullable=False)  # JSON 字符串，包含推荐列表
    pushed = db.Column(db.Boolean, default=False)

    tracks = db.relationship("RecommendationTrack", backref="report", lazy="dynamic", cascade="all, delete-orphan")


class RecommendationTrack(db.Model):
    """
    推荐准确率追踪

    报告生成时为每条推荐创建一条记录，后续定时任务回填实际价格。
    outcome 字段在 N 天后根据价格走势自动判定。
    """
    __tablename__ = "recommendation_tracks"
    __table_args__ = (
        db.UniqueConstraint("report_id", "ticker", name="uq_report_ticker"),
    )

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("daily_reports.id"), nullable=False, index=True)
    ticker = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    market = db.Column(db.String(20), nullable=False)

    direction = db.Column(db.String(10), nullable=False)  # buy / sell
    entry_price = db.Column(db.Float, nullable=False)
    stop_loss = db.Column(db.Float, nullable=False)
    take_profit_1 = db.Column(db.Float, nullable=False)
    take_profit_2 = db.Column(db.Float, nullable=False)
    confidence = db.Column(db.Integer, default=0)

    price_after_1d = db.Column(db.Float)
    price_after_3d = db.Column(db.Float)
    price_after_5d = db.Column(db.Float)
    price_after_10d = db.Column(db.Float)

    hit_tp1 = db.Column(db.Boolean)
    hit_tp2 = db.Column(db.Boolean)
    hit_sl = db.Column(db.Boolean)
    outcome = db.Column(db.String(20))  # win / loss / partial / pending / expired

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeepAnalysisCache(db.Model):
    """个股深度分析缓存（避免短时间重复计算）"""
    __tablename__ = "deep_analysis_cache"
    __table_args__ = (
        db.UniqueConstraint("ticker", "market", name="uq_deep_ticker_market"),
    )

    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False, index=True)
    market = db.Column(db.String(20), nullable=False)
    data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
