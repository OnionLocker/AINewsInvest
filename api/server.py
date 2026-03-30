"""FastAPI application entry-point.

Creates the app, registers CORS, includes routers, serves SPA.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = PROJECT_ROOT / "web" / "dist"

from api.routes.auth import router as auth_router
from api.routes.admin import router as admin_router
from api.routes.recommendations import router as recs_router
from api.routes.user import router as user_router
from api.routes.analysis import router as analysis_router

app = FastAPI(title="Alpha Vault API", version="2.0.0")

# CORS
_default_origins = [
    "http://127.0.0.1:5173", "http://localhost:5173",
    "http://127.0.0.1:3000", "http://localhost:3000",
]
_origins_raw = (os.getenv("APP_CORS_ALLOW_ORIGINS") or "").strip()
_origins = [s.strip() for s in _origins_raw.split(",") if s.strip()] if _origins_raw else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(recs_router)
app.include_router(user_router)
app.include_router(analysis_router)


@app.get("/healthz")
async def healthz(response: Response):
    import sqlite3
    from core.user import SYSTEM_DB_PATH

    checks: dict[str, dict[str, Any]] = {"process": {"ok": True}}
    ready = True

    try:
        with sqlite3.connect(str(SYSTEM_DB_PATH), timeout=2) as conn:
            conn.execute("SELECT 1").fetchone()
        checks["system_db"] = {"ok": True}
    except Exception as exc:
        ready = False
        checks["system_db"] = {"ok": False, "detail": str(exc)}

    if not ready:
        response.status_code = 503

    return {
        "status": "ok" if ready else "degraded",
        "ready": ready,
        "time": datetime.utcnow().isoformat(),
        "checks": checks,
    }


# SPA serving
if FRONTEND_DIST_DIR.exists():
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(
            FRONTEND_DIST_DIR / "index.html",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "healthz":
            from fastapi import HTTPException
            raise HTTPException(404, "Not found")
        asset = (FRONTEND_DIST_DIR / full_path).resolve()
        try:
            asset.relative_to(FRONTEND_DIST_DIR.resolve())
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(404, "Not found")
        if asset.is_file():
            headers = {}
            if "/assets/" in full_path:
                headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                headers["Cache-Control"] = "no-cache"
            return FileResponse(asset, headers=headers)
        return FileResponse(FRONTEND_DIST_DIR / "index.html",
                            headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
