"""
config.py - Flask 应用配置

敏感信息从 .env 读取（SECRET_KEY, ENCRYPT_KEY），
业务参数从 config.yaml 热重载（通过 utils/config_loader.py）。
"""
import os
from dotenv import load_dotenv

_project_root = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_project_root, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = "sqlite:///ainews.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
