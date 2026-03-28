"""FastAPI dependencies - JWT auth, request models, user injection."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from loguru import logger
from pydantic import BaseModel

from core.user import User, UserManager, LoginThrottledError

SECRET_KEY = os.getenv("JWT_SECRET", "alpha-vault-dev-secret-change-me")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "72"))

security = HTTPBearer(auto_error=False)


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.user_id),
        "username": user.username,
        "is_admin": user.is_admin,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid or expired")


def get_user_manager() -> UserManager:
    return UserManager()


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(creds.credentials)
    user_id = int(payload["sub"])
    um = get_user_manager()
    try:
        user = um.get_user_by_id(user_id)
    finally:
        um.close()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# -- Pydantic request models --

class AuthRequest(BaseModel):
    username: str
    password: str

class AdminBootstrapRequest(BaseModel):
    username: str
    password: str

class ScreenRequest(BaseModel):
    market: str = "us_stock"
    top_n: int = 20
    ref_date: Optional[str] = None

class WatchlistAddRequest(BaseModel):
    ticker: str
    name: str
    market: str
    recommendation_item_id: Optional[int] = None
    note: str = ""

class StockQueryRequest(BaseModel):
    ticker: str
    market: str

class AdminRecommendationRunRequest(BaseModel):
    market: str = "all"
    force: bool = False
    note: str = ""

class DeepAnalysisRequest(BaseModel):
    ticker: str
    market: str
    force: bool = False
