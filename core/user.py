"""User management  - registration, login, JWT, admin roles.

Modelled after astock-quant/core/user.py with simplified password hashing
(using hashlib + salt rather than an external bcrypt dependency).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

SYSTEM_DB_DIR = Path("./data")
SYSTEM_DB_PATH = SYSTEM_DB_DIR / "system.db"

MIN_PASSWORD_LENGTH = 1
MAX_LOGIN_FAILURES = int(os.getenv("AUTH_MAX_LOGIN_FAILURES", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("AUTH_LOGIN_LOCKOUT_MINUTES", "15"))


@dataclass
class User:
    user_id: int
    username: str
    is_admin: bool = False

    @property
    def data_dir(self) -> Path:
        return Path(f"./data/users/{self.username}")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "research.db"


class LoginThrottledError(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__("login throttled")
        self.retry_after_seconds = max(int(retry_after_seconds), 1)


class UserManager:
    """User CRUD, login throttling, admin bootstrap, system settings."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = SYSTEM_DB_PATH
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                is_admin      BOOLEAN DEFAULT 0,
                is_active     BOOLEAN DEFAULT 1,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS system_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS login_attempts (
                username     TEXT PRIMARY KEY,
                failed_count INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT DEFAULT NULL,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()

    @staticmethod
    def _generate_salt() -> str:
        return secrets.token_hex(16)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def admin_exists(self) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE is_admin = 1"
        ).fetchone()
        return row["cnt"] > 0

    def register(self, username: str, password: str, is_admin: bool = False) -> User:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位")

        existing = self._conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            raise ValueError("该用户名已被注册")

        salt = self._generate_salt()
        pw_hash = self._hash_password(password, salt)
        cur = self._conn.execute(
            "INSERT INTO users (username, password_hash, salt, is_admin) VALUES (?, ?, ?, ?)",
            (username, pw_hash, salt, 1 if is_admin else 0),
        )
        self._conn.commit()
        user_id = cur.lastrowid

        user = User(user_id=user_id, username=username, is_admin=is_admin)
        user.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"用户注册: {username} (admin={is_admin})")
        return user

    def bootstrap_admin(self, username: str, password: str) -> User:
        if self.admin_exists():
            raise ValueError("管理员已存在，无法重复创建")
        return self.register(username, password, is_admin=True)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _check_throttle(self, username: str):
        row = self._conn.execute(
            "SELECT failed_count, locked_until FROM login_attempts WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return
        if row["locked_until"]:
            locked = datetime.fromisoformat(row["locked_until"])
            if datetime.utcnow() < locked:
                remaining = int((locked - datetime.utcnow()).total_seconds())
                raise LoginThrottledError(remaining)

    def _record_failure(self, username: str):
        row = self._conn.execute(
            "SELECT failed_count FROM login_attempts WHERE username = ?",
            (username,),
        ).fetchone()
        if row:
            count = row["failed_count"] + 1
            locked_until = None
            if count >= MAX_LOGIN_FAILURES:
                locked_until = (
                    datetime.utcnow() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
                ).isoformat()
            self._conn.execute(
                "UPDATE login_attempts SET failed_count=?, locked_until=?, updated_at=CURRENT_TIMESTAMP WHERE username=?",
                (count, locked_until, username),
            )
        else:
            self._conn.execute(
                "INSERT INTO login_attempts (username, failed_count) VALUES (?, 1)",
                (username,),
            )
        self._conn.commit()

    def _clear_failures(self, username: str):
        self._conn.execute(
            "DELETE FROM login_attempts WHERE username = ?", (username,)
        )
        self._conn.commit()

    def authenticate(self, username: str, password: str) -> User:
        self._check_throttle(username)

        row = self._conn.execute(
            "SELECT id, username, password_hash, salt, is_admin, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            self._record_failure(username)
            raise ValueError("用户名或密码错误")

        if not row["is_active"]:
            raise ValueError("该账号已被禁用")

        expected = self._hash_password(password, row["salt"])
        if row["password_hash"] != expected:
            self._record_failure(username)
            raise ValueError("用户名或密码错误")

        self._clear_failures(username)
        return User(
            user_id=row["id"],
            username=row["username"],
            is_admin=bool(row["is_admin"]),
        )

    # ------------------------------------------------------------------
    # User queries
    # ------------------------------------------------------------------

    def get_user_by_id(self, user_id: int) -> User | None:
        row = self._conn.execute(
            "SELECT id, username, is_admin FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return User(user_id=row["id"], username=row["username"], is_admin=bool(row["is_admin"]))

    def list_users(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, username, is_admin, is_active, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def set_user_active(self, username: str, active: bool):
        self._conn.execute(
            "UPDATE users SET is_active = ? WHERE username = ?",
            (1 if active else 0, username),
        )
        self._conn.commit()

    def delete_user(self, username: str):
        self._conn.execute("DELETE FROM users WHERE username = ?", (username,))
        self._conn.commit()
        logger.info(f"用户删除: {username}")

    # ------------------------------------------------------------------
    # System settings
    # ------------------------------------------------------------------

    def get_setting(self, key: str, default: str = "") -> str:
        row = self._conn.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self._conn.execute(
            "INSERT INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, value),
        )
        self._conn.commit()
