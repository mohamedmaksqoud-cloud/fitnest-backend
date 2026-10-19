"""Password hashing (bcrypt) and JWT helpers."""

import hashlib
import secrets
from datetime import timedelta

from jose import JWTError, jwt

from app.config import settings
from app.models import utcnow

import bcrypt

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5


# ---------- Passwords ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- OTP ----------
def generate_otp() -> str:
    """Cryptographically secure 6-digit code."""
    return f"{secrets.randbelow(900_000) + 100_000:06d}"


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


# ---------- JWT ----------
def create_access_token(user_id: int) -> str:
    expire = utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Return the user id from a token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None
