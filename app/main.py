"""FitNest API — FastAPI backend for the FitNest Android app."""

import logging
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text

from app.config import settings
from app.database import Base, engine
from app.routers import admin, ai, auth

logger = logging.getLogger("fitnest")

BASE_DIR = Path(__file__).resolve().parent.parent  # repo root (holds static/)

# Create tables at import time: serverless platforms (Vercel/Mangum) never run
# the ASGI lifespan, so a lifespan-only create_all would leave the DB empty.
# Never let a DB hiccup kill the whole app at startup.
try:
    Base.metadata.create_all(bind=engine)
except Exception as exc:  # noqa: BLE001 - startup must be bulletproof
    logger.warning("create_all failed at startup: %s", exc)

limiter = Limiter(key_func=get_remote_address)


app = FastAPI(title="FitNest API", version="1.0.0")


@app.middleware("http")
async def restore_original_path(request: Request, call_next):
    """Vercel's rewrite behavior delivers the rewritten path (/api/index) to
    the function and drops the original URL. The original path is smuggled
    through the __p__ query param (see vercel.json) — restore it here so the
    router sees the real path."""
    raw_qs = request.scope.get("query_string", b"").decode("latin-1")
    original, rest = None, []
    for key, value in parse_qsl(raw_qs, keep_blank_values=True):
        if key == "__p__" and original is None:
            original = value
        else:
            rest.append((key, value))
    if original:
        request.scope["path"] = original
        request.scope["query_string"] = urlencode(rest).encode("latin-1")
    return await call_next(request)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=429, content={"detail": "طلبات كثيرة جداً — حاول لاحقاً"}
    ),
)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(ai.router)

# Exercise demo videos (bundled in repo so they survive free-tier deploys).
# Absolute path: serverless functions don't start in the project root.
# If the bundle lacks static/, keep the API alive (videos just 404).
_static_dir = BASE_DIR / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
else:
    logger.warning("static dir missing at %s — /static disabled", _static_dir)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug")
def debug(request: Request):
    """Non-sensitive diagnostics: what the server sees (no secrets)."""
    videos_dir = BASE_DIR / "static" / "videos"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        db_ok = f"unreachable: {type(exc).__name__}"
    return {
        "scope_path": request.scope.get("path"),
        "root_path": request.scope.get("root_path"),
        "headers": {k: v for k, v in request.headers.items()
                    if "vercel" in k.lower() or "forwarded" in k.lower() or "uri" in k.lower()},
        "static_exists": _static_dir.is_dir(),
        "videos": sorted(p.name for p in videos_dir.glob("*")) if videos_dir.is_dir() else [],
        "db_scheme": settings.DATABASE_URL.split("://")[0] if "://" in settings.DATABASE_URL else "?",
        "db_reachable": db_ok,
        "smtp_configured": settings.smtp_configured,
        "gemini_configured": settings.gemini_configured,
    }


@app.get("/")
def root():
    return {"app": "FitNest API", "version": "1.0.0"}


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
def echo_path(full_path: str, request: Request):
    """TEMPORARY diagnostic: shows exactly what the serverless platform delivers."""
    return {
        "caught_path": full_path,
        "scope_path": request.scope.get("path"),
        "root_path": request.scope.get("root_path"),
        "method": request.method,
        "headers": dict(request.headers),
        "query": dict(request.query_params),
    }
