"""Authentication endpoints: register / verify / login / password reset / profile."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app import emailer
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import OTPCode, User, utcnow
from app.schemas import (
    ForgotIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    ResendIn,
    ResetIn,
    TokenOut,
    UserOut,
    VerifyIn,
)
from app.security import (
    OTP_MAX_ATTEMPTS,
    OTP_TTL_MINUTES,
    create_access_token,
    generate_otp,
    hash_otp,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

RESEND_MAX_PER_HOUR = 3


def _get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.strip().lower()).first()


def _issue_otp(db: Session, user: User, purpose: str, is_resend: bool = False) -> str:
    """Create a fresh OTP row (clearing expired ones of the same purpose) and return the code."""
    db.query(OTPCode).filter(
        OTPCode.user_id == user.id,
        OTPCode.purpose == purpose,
        OTPCode.expires_at < utcnow(),
    ).delete(synchronize_session=False)
    code = generate_otp()
    db.add(
        OTPCode(
            user_id=user.id,
            code_hash=hash_otp(code),
            purpose=purpose,
            expires_at=utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
            is_resend=is_resend,
        )
    )
    db.commit()
    return code


def _check_otp(db: Session, user: User, purpose: str, code: str) -> None:
    """Validate an OTP or raise an HTTP error. Consumes attempts; deletes on success."""
    otp = (
        db.query(OTPCode)
        .filter(OTPCode.user_id == user.id, OTPCode.purpose == purpose)
        .order_by(OTPCode.created_at.desc())
        .first()
    )
    if otp is None or otp.expires_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "الرمز غير صالح أو منتهي الصلاحية")
    if otp.attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "تجاوزت عدد المحاولات المسموح — اطلب رمزاً جديداً"
        )
    otp.attempts += 1
    db.commit()
    if otp.code_hash != hash_otp(code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "الرمز غير صحيح")
    # Success: remove all OTPs of this purpose for the user
    db.query(OTPCode).filter(
        OTPCode.user_id == user.id, OTPCode.purpose == purpose
    ).delete(synchronize_session=False)
    db.commit()


def _token_response(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id),
        is_admin=user.is_admin,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if _get_user_by_email(db, email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "هذا البريد مسجّل بالفعل")

    is_admin = bool(settings.ADMIN_EMAIL) and email == settings.ADMIN_EMAIL.strip().lower()
    user = User(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        is_verified=False,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    code = _issue_otp(db, user, OTPCode.PURPOSE_VERIFY)
    emailer.send_otp_email(user.email, user.name, code, purpose="verify")

    return MessageOut(message="تم إنشاء الحساب — أرسلنا رمز تحقق إلى بريدك الإلكتروني")


@router.post("/verify", response_model=TokenOut)
@limiter.limit("10/minute")
def verify(request: Request, body: VerifyIn, db: Session = Depends(get_db)):
    user = _get_user_by_email(db, body.email)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "الرمز غير صالح أو منتهي الصلاحية")
    _check_otp(db, user, OTPCode.PURPOSE_VERIFY, body.code)
    user.is_verified = True
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/resend-code", response_model=MessageOut)
@limiter.limit("5/minute")
def resend_code(request: Request, body: ResendIn, db: Session = Depends(get_db)):
    # Always return 200 to avoid revealing whether the email exists.
    user = _get_user_by_email(db, body.email)
    if user is not None and not user.is_verified:
        one_hour_ago = utcnow() - timedelta(hours=1)
        recent = (
            db.query(OTPCode)
            .filter(
                OTPCode.user_id == user.id,
                OTPCode.purpose == OTPCode.PURPOSE_VERIFY,
                OTPCode.is_resend.is_(True),
                OTPCode.created_at >= one_hour_ago,
            )
            .count()
        )
        if recent >= RESEND_MAX_PER_HOUR:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "تجاوزت الحد المسموح — حاول مرة أخرى بعد ساعة",
            )
        code = _issue_otp(db, user, OTPCode.PURPOSE_VERIFY, is_resend=True)
        emailer.send_otp_email(user.email, user.name, code, purpose="verify")
    return MessageOut(message="إذا كان البريد مسجلاً وغير مؤكد، ستصلك رسالة برمز جديد")


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)):
    user = _get_user_by_email(db, body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "البريد أو كلمة المرور غير صحيحة")
    if not user.is_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "الحساب غير مؤكد — أدخل رمز التحقق المرسل إلى بريدك"
        )
    return _token_response(user)


@router.post("/forgot-password", response_model=MessageOut)
@limiter.limit("5/minute")
def forgot_password(request: Request, body: ForgotIn, db: Session = Depends(get_db)):
    # Always return 200 — never reveal whether the email exists.
    user = _get_user_by_email(db, body.email)
    if user is not None:
        code = _issue_otp(db, user, OTPCode.PURPOSE_RESET)
        emailer.send_otp_email(user.email, user.name, code, purpose="reset")
    return MessageOut(message="إذا كان البريد مسجلاً، ستصلك رسالة برمز إعادة التعيين")


@router.post("/reset-password", response_model=MessageOut)
@limiter.limit("10/minute")
def reset_password(request: Request, body: ResetIn, db: Session = Depends(get_db)):
    user = _get_user_by_email(db, body.email)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "الرمز غير صالح أو منتهي الصلاحية")
    _check_otp(db, user, OTPCode.PURPOSE_RESET, body.code)
    user.password_hash = hash_password(body.new_password)
    # Resetting via an emailed code proves email ownership — verify the account too.
    user.is_verified = True
    db.commit()
    return MessageOut(message="تم تغيير كلمة المرور بنجاح — سجّل الدخول الآن")


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return UserOut.model_validate(current)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(current)
    db.commit()
    return None
