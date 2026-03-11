"""
models.py - SQLAlchemy 数据模型

TG Token 在数据库中以 Fernet 密文存储（tg_bot_token_enc / tg_chat_id_enc），
set_tg_config / get_tg_config 封装了加解密逻辑，对外透明。
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    # Telegram 密文字段（Fernet 加密后的 base64 字符串）
    tg_bot_token_enc = db.Column(db.Text, default="")
    tg_chat_id_enc = db.Column(db.Text, default="")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def set_tg_config(self, bot_token: str, chat_id: str):
        """加密并保存 Telegram 配置"""
        from utils.crypto import encrypt
        self.tg_bot_token_enc = encrypt(bot_token) if bot_token else ""
        self.tg_chat_id_enc = encrypt(chat_id) if chat_id else ""

    def get_tg_config(self) -> tuple[str, str]:
        """解密并返回 (bot_token, chat_id)，未配置时返回空字符串"""
        from utils.crypto import decrypt
        token = decrypt(self.tg_bot_token_enc) if self.tg_bot_token_enc else ""
        chat_id = decrypt(self.tg_chat_id_enc) if self.tg_chat_id_enc else ""
        return token, chat_id

    @property
    def tg_configured(self) -> bool:
        return bool(self.tg_bot_token_enc and self.tg_chat_id_enc)

    def __repr__(self):
        return f"<User {self.username}>"
