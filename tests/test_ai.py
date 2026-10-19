"""Smoke tests for POST /ai/chat (FitCoach). Gemini calls are mocked — no network."""

import os
import tempfile
from datetime import datetime, timezone

# Isolate the DB *before* importing the app (settings are read at import time).
_tmpdir = tempfile.mkdtemp(prefix="fitnest-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ.pop("GEMINI_API_KEY", None)

import pytest
from fastapi.testclient import TestClient

import app.routers.ai as ai_router
from app.ai_client import AIProviderError
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import AiUsage, User
from app.security import create_access_token, hash_password


@pytest.fixture()
def client():
    with TestClient(app) as c:  # lifespan creates tables in the temp DB
        yield c


@pytest.fixture()
def user():
    db = SessionLocal()
    u = User(
        name="Test User",
        email=f"user-{datetime.now(timezone.utc).timestamp()}@test.com",
        password_hash=hash_password("password123"),
        is_verified=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


def _headers(uid):
    return {"Authorization": f"Bearer {create_access_token(uid)}"}


def _set_key(monkeypatch, value):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", value)


def _mock_reply(monkeypatch, text="أهلاً! جرّب ٣ مجموعات ضغط 💪", exc=None):
    calls = {}

    def fake(message, history=None):
        calls["message"] = message
        calls["history"] = history
        if exc is not None:
            raise exc
        return text

    monkeypatch.setattr(ai_router, "generate_reply", fake)
    return calls


def _usage_count(uid):
    db = SessionLocal()
    row = (
        db.query(AiUsage)
        .filter(
            AiUsage.user_id == uid,
            AiUsage.day == datetime.now(timezone.utc).date(),
        )
        .first()
    )
    n = row.count if row else 0
    db.close()
    return n


# ---------- auth ----------
def test_chat_requires_auth(client):
    r = client.post("/ai/chat", json={"message": "hi"})
    assert r.status_code == 401


def test_chat_rejects_bad_token(client):
    r = client.post(
        "/ai/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


# ---------- 503 when key missing ----------
def test_chat_503_without_key(client, user, monkeypatch):
    _set_key(monkeypatch, "")
    r = client.post("/ai/chat", json={"message": "hi"}, headers=_headers(user))
    assert r.status_code == 503
    assert "AI service not configured" in r.json()["detail"]


# ---------- happy path ----------
def test_chat_happy_path(client, user, monkeypatch):
    _set_key(monkeypatch, "test-key")
    calls = _mock_reply(monkeypatch)
    r = client.post(
        "/ai/chat", json={"message": "عايز تمرين صدر"}, headers=_headers(user)
    )
    assert r.status_code == 200
    body = r.json()
    assert "جرّب ٣ مجموعات ضغط" in body["reply"]
    assert body["remaining_today"] == 19
    assert calls["message"] == "عايز تمرين صدر"
    assert _usage_count(user) == 1


def test_chat_passes_history(client, user, monkeypatch):
    _set_key(monkeypatch, "test-key")
    calls = _mock_reply(monkeypatch)
    history = [
        {"role": "user", "content": "أنا مبتدئ"},
        {"role": "assistant", "content": "تمام، نبدأ بخطة خفيفة"},
    ]
    r = client.post(
        "/ai/chat",
        json={"message": "وبعدين؟", "history": history},
        headers=_headers(user),
    )
    assert r.status_code == 200
    assert calls["history"] == [("user", "أنا مبتدئ"), ("assistant", "تمام، نبدأ بخطة خفيفة")]
    assert r.json()["remaining_today"] == 19  # first request for this user today


# ---------- rate limit ----------
def test_chat_rate_limit_429(client, user, monkeypatch):
    _set_key(monkeypatch, "test-key")
    _mock_reply(monkeypatch)
    db = SessionLocal()
    db.add(
        AiUsage(
            user_id=user,
            day=datetime.now(timezone.utc).date(),
            count=20,
        )
    )
    db.commit()
    db.close()
    r = client.post("/ai/chat", json={"message": "hi"}, headers=_headers(user))
    assert r.status_code == 429
    assert "Daily limit" in r.json()["detail"]
    assert _usage_count(user) == 20  # not incremented past the cap


# ---------- provider failure → 502 ----------
def test_chat_provider_error_is_502(client, user, monkeypatch):
    _set_key(monkeypatch, "test-key")
    _mock_reply(monkeypatch, exc=AIProviderError("boom"))
    r = client.post("/ai/chat", json={"message": "hi"}, headers=_headers(user))
    assert r.status_code == 502
    assert "try again later" in r.json()["detail"]
    # the request still counted against the daily quota
    assert _usage_count(user) == 1


# ---------- validation ----------
@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},  # too short
        {"message": "x" * 1001},  # too long
        {"message": "hi", "history": [{"role": "user", "content": "x"}] * 11},  # >10
        {"message": "hi", "history": [{"role": "bot", "content": "x"}]},  # bad role
        {"message": "hi", "history": [{"role": "user", "content": ""}]},  # empty content
        {},  # missing message
    ],
)
def test_chat_validation_422(client, user, monkeypatch, payload):
    _set_key(monkeypatch, "test-key")
    _mock_reply(monkeypatch)
    r = client.post("/ai/chat", json=payload, headers=_headers(user))
    assert r.status_code == 422
