"""Authentication routes  - register, login, admin bootstrap."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.deps import (
    AuthRequest, AdminBootstrapRequest,
    create_token, get_user_manager,
)
from core.user import LoginThrottledError

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/bootstrap-status")
async def bootstrap_status():
    um = get_user_manager()
    try:
        exists = um.admin_exists()
    finally:
        um.close()
    return {"admin_exists": exists}


@router.post("/bootstrap-admin")
async def bootstrap_admin(req: AdminBootstrapRequest):
    um = get_user_manager()
    try:
        user = um.bootstrap_admin(req.username, req.password)
        token = create_token(user)
        return {"token": token, "username": user.username, "is_admin": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        um.close()


@router.post("/register")
async def register(req: AuthRequest):
    um = get_user_manager()
    try:
        if not um.admin_exists():
            raise HTTPException(status_code=400, detail="Please bootstrap admin first")
        user = um.register(req.username, req.password)
        token = create_token(user)
        return {"token": token, "username": user.username, "is_admin": False}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        um.close()


@router.post("/login")
async def login(req: AuthRequest):
    um = get_user_manager()
    try:
        user = um.authenticate(req.username, req.password)
        token = create_token(user)
        return {"token": token, "username": user.username, "is_admin": user.is_admin}
    except LoginThrottledError as e:
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts, retry after {e.retry_after_seconds}s",
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    finally:
        um.close()


@router.post("/admin-login")
async def admin_login(req: AuthRequest):
    um = get_user_manager()
    try:
        user = um.authenticate(req.username, req.password)
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Not an admin account")
        token = create_token(user)
        return {"token": token, "username": user.username, "is_admin": True}
    except LoginThrottledError as e:
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts, retry after {e.retry_after_seconds}s",
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    finally:
        um.close()


from fastapi import Depends as _Depends
from api.deps import get_current_user as _get_current_user
from core.user import User as _User

@router.get("/me")
async def auth_me(user: _User = _Depends(_get_current_user)):
    return {"user_id": user.user_id, "username": user.username, "is_admin": user.is_admin}
