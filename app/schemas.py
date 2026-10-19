"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth requests ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class VerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendIn(BaseModel):
    email: EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)


# ---------- Shared ----------
class UserOut(BaseModel):
    id: int
    name: str
    email: str
    is_verified: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    message: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_admin: bool
    user: UserOut


# ---------- AI chat (FitCoach) ----------
class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatHistoryMessage] | None = Field(default=None, max_length=10)


class ChatOut(BaseModel):
    reply: str
    remaining_today: int


# ---------- Admin ----------
class AdminUserOut(BaseModel):
    id: int
    name: str
    email: str
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedUsersOut(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    per_page: int


class StatsOut(BaseModel):
    total_users: int
    verified_users: int
    signups_last_7_days: int
    signups_last_30_days: int
