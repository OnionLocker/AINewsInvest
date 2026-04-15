# -*- coding: utf-8 -*-
"""Tests for API auth dependencies (api.deps).

Tests cover:
  - JWT token creation and verification
  - get_current_user raises 401 without credentials
  - verify_token raises 401 for invalid/expired tokens

All tests are self-contained; no running server required.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jose import jwt

from api.deps import (
    ALGORITHM,
    SECRET_KEY,
    TOKEN_EXPIRE_HOURS,
    create_token,
    verify_token,
)


# ===================================================================
# create_token
# ===================================================================

class TestCreateToken:

    def _make_user(self, user_id=1, username="testuser", is_admin=False):
        user = MagicMock()
        user.user_id = user_id
        user.username = username
        user.is_admin = is_admin
        return user

    def test_creates_valid_jwt(self):
        user = self._make_user()
        token = create_token(user)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "1"
        assert payload["username"] == "testuser"
        assert payload["is_admin"] is False

    def test_admin_flag_set(self):
        user = self._make_user(is_admin=True)
        token = create_token(user)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["is_admin"] is True

    def test_token_has_expiry(self):
        user = self._make_user()
        token = create_token(user)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload
        # Expiry should be roughly TOKEN_EXPIRE_HOURS from now
        exp = datetime.utcfromtimestamp(payload["exp"])
        delta = exp - datetime.utcnow()
        # Allow 60 seconds tolerance
        assert abs(delta.total_seconds() - TOKEN_EXPIRE_HOURS * 3600) < 60


# ===================================================================
# verify_token
# ===================================================================

class TestVerifyToken:

    def test_valid_token(self):
        payload = {
            "sub": "1",
            "username": "testuser",
            "is_admin": False,
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        result = verify_token(token)
        assert result["sub"] == "1"
        assert result["username"] == "testuser"

    def test_expired_token_raises_401(self):
        payload = {
            "sub": "1",
            "username": "testuser",
            "is_admin": False,
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_token("this.is.not.a.valid.token")
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        payload = {
            "sub": "1",
            "username": "testuser",
            "is_admin": False,
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401


# ===================================================================
# get_current_user (async dependency)
# ===================================================================

class TestGetCurrentUser:

    def test_no_credentials_raises_401(self):
        import asyncio
        from api.deps import get_current_user
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_current_user(creds=None))
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail
