"""FitCoach AI chat endpoint: POST /ai/chat (JWT required, 20 requests/day/user)."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai_client import AIProviderError, generate_reply
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import AiUsage, User
from app.schemas import ChatIn, ChatOut

router = APIRouter(prefix="/ai", tags=["ai"])

AI_DAILY_LIMIT = 20

MSG_NOT_CONFIGURED = (
    "خدمة الذكاء الاصطناعي غير مُعدّة بعد — تواصل مع إدارة التطبيق"
    " | AI service not configured"
)
MSG_LIMIT_REACHED = (
    f"وصلت إلى الحد اليومي ({AI_DAILY_LIMIT} رسالة) — عُد غداً"
    f" | Daily limit reached ({AI_DAILY_LIMIT} messages) — come back tomorrow"
)
MSG_PROVIDER_DOWN = (
    "تعذّر الوصول إلى المساعد الذكي — حاول لاحقاً"
    " | AI assistant unavailable — try again later"
)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _get_usage(db: Session, user_id: int) -> AiUsage:
    usage = (
        db.query(AiUsage)
        .filter(AiUsage.user_id == user_id, AiUsage.day == _today())
        .first()
    )
    if usage is None:
        usage = AiUsage(user_id=user_id, day=_today(), count=0)
        db.add(usage)
        db.commit()
        db.refresh(usage)
    return usage


@router.post("/chat", response_model=ChatOut)
def chat(
    body: ChatIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatOut:
    if not settings.gemini_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_NOT_CONFIGURED)

    usage = _get_usage(db, current.id)
    if usage.count >= AI_DAILY_LIMIT:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MSG_LIMIT_REACHED)

    # Count the request before calling the provider (protects the API quota).
    usage.count += 1
    db.commit()

    history = [(m.role, m.content) for m in body.history] if body.history else []
    try:
        reply = generate_reply(body.message, history)
    except AIProviderError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, MSG_PROVIDER_DOWN)

    return ChatOut(reply=reply, remaining_today=AI_DAILY_LIMIT - usage.count)
