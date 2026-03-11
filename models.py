"""
models.py - SQLAlchemy 数据模型

User     → 用户账号 + Telegram 加密配置
Watchlist → 用户自选标的
DailyReport → 每日 AI 投研报告
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
