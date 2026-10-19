"""FitNest API — FastAPI backend for the FitNest Android app."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import settings
from app.database import Base, engine
from app.routers import admin, ai, auth

BASE_DIR = Path(__file__).resolve().parent.parent  # repo root (holds static/)

# Create tables at import time: serverless platforms (Vercel/Mangum) never run
# the ASGI lifespan, so a lifespan-only create_all would leave the DB empty.
Base.metadata.create_all(bind=engine)

limiter = Limiter(key_func=get_remote_address)


app = FastAPI(title="FitNest API", version="1.0.0")

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
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"app": "FitNest API", "version": "1.0.0"}
