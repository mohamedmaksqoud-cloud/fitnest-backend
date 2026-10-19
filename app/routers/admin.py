"""Admin-only endpoints: user list and signup stats."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import User, utcnow
from app.schemas import AdminUserOut, PaginatedUsersOut, StatsOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=PaginatedUsersOut)
def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    total = db.query(User).count()
    users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return PaginatedUsersOut(
        items=[AdminUserOut.model_validate(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    now = utcnow()
    return StatsOut(
        total_users=db.query(User).count(),
        verified_users=db.query(User).filter(User.is_verified.is_(True)).count(),
        signups_last_7_days=db.query(User)
        .filter(User.created_at >= now - timedelta(days=7))
        .count(),
        signups_last_30_days=db.query(User)
        .filter(User.created_at >= now - timedelta(days=30))
        .count(),
    )
