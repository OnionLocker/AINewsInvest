"""
utils/crypto.py - 对称加密工具（Fernet）

借鉴 QuantProject：用 Fernet (AES-128-CBC + HMAC) 加密用户的 Telegram Token
等敏感数据，数据库中只存密文，运行时按需解密。
密钥从 .env 的 ENCRYPT_KEY 读取，首次部署由 deploy.sh 自动生成。
"""
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    key = os.getenv("ENCRYPT_KEY", "")
    if not key:
        raise RuntimeError("未找到 ENCRYPT_KEY，请运行 deploy.sh 或手动生成")
    _fernet = Fernet(key.encode())
    return _fernet


def encrypt(plain: str) -> str:
    """加密明文字符串，返回 base64 密文"""
    if not plain:
        return ""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt(cipher: str) -> str:
    """解密密文，返回原始字符串"""
    if not cipher:
        return ""
    return _get_fernet().decrypt(cipher.encode()).decode()


if __name__ == "__main__":
    key = Fernet.generate_key().decode()
    env_path = os.path.join(_project_root, ".env")
    existing = ""
    if os.path.exists(env_path):
        with open(env_path) as f:
            existing = f.read()
    if "ENCRYPT_KEY" in existing:
        print("ENCRYPT_KEY 已存在，未覆盖。")
    else:
        with open(env_path, "a") as f:
            f.write(f"\nENCRYPT_KEY={key}\n")
        print(f"ENCRYPT_KEY 已写入 .env: {key}")
