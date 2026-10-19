"""SQLAlchemy models."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    """Naive UTC datetime (keeps SQLite and Postgres comparisons consistent)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    otps = relationship("OTPCode", back_populates="user", cascade="all, delete-orphan")


class OTPCode(Base):
    """One-time codes for email verification and password reset.

    The code itself is stored as a SHA-256 hash (never plaintext).
    """

    __tablename__ = "otp_codes"

    PURPOSE_VERIFY = "verify"
    PURPOSE_RESET = "reset"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    purpose = Column(String(16), nullable=False)  # verify | reset
    attempts = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    # True when this OTP was created via /auth/resend-code (used for the 3/hour limit)
    is_resend = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="otps")


class AiUsage(Base):
    """Per-user daily counter for the FitCoach AI chat (20 requests/day)."""

    __tablename__ = "ai_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_ai_usage_user_day"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    day = Column(Date, nullable=False, index=True)
    count = Column(Integer, default=0, nullable=False)
