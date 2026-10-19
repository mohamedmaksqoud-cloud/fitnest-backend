"""SMTP email sending with an Arabic RTL HTML template for OTP codes."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger("fitnest.email")


def _otp_html(name: str, code: str, purpose: str) -> str:
    if purpose == "reset":
        title = "إعادة تعيين كلمة المرور"
        intro = "طلبت إعادة تعيين كلمة المرور الخاصة بك."
    else:
        title = "تأكيد بريدك الإلكتروني"
        intro = "مرحباً بك في FitNest! استخدم الرمز التالي لتأكيد حسابك."

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Tahoma,Arial,sans-serif;">
  <div style="max-width:480px;margin:40px auto;background:#ffffff;border-radius:16px;
              padding:32px 28px;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,0.06);">
    <div style="font-size:28px;font-weight:800;color:#16a34a;margin-bottom:8px;">FitNest 💪</div>
    <h2 style="color:#111827;margin:8px 0 4px;">{title}</h2>
    <p style="color:#4b5563;font-size:15px;">{intro}</p>
    <p style="color:#6b7280;font-size:14px;">أهلاً {name}، رمز التحقق الخاص بك هو:</p>
    <div style="font-size:38px;font-weight:800;letter-spacing:10px;color:#111827;
                background:#f0fdf4;border:2px dashed #16a34a;border-radius:12px;
                padding:14px 8px;margin:16px 0;" dir="ltr">{code}</div>
    <p style="color:#9ca3af;font-size:13px;">صالح لمدة 10 دقائق فقط. لا تشاركه مع أي شخص.</p>
    <p style="color:#9ca3af;font-size:12px;margin-top:24px;">إذا لم تطلب هذا الرمز، تجاهل هذه الرسالة.</p>
  </div>
</body>
</html>"""


def _send(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email. Returns False (with a clear log) if SMTP is misconfigured."""
    if not settings.smtp_configured:
        logger.warning(
            "SMTP is not configured — email to %s was NOT sent. "
            "Set SMTP_HOST/SMTP_USER/SMTP_PASS (see .env.example).",
            to_email,
        )
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if settings.SMTP_TLS:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        try:
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)
        finally:
            server.quit()
        logger.info("OTP email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send email to %s — check SMTP settings", to_email)
        return False


def send_otp_email(to_email: str, name: str, code: str, purpose: str = "verify") -> bool:
    """Send the 6-digit OTP. In dev (no SMTP), logs the code so local testing works."""
    subject = (
        "رمز إعادة تعيين كلمة المرور — FitNest"
        if purpose == "reset"
        else "رمز تأكيد حسابك — FitNest"
    )
    sent = _send(to_email, subject, _otp_html(name, code, purpose))
    if not sent and not settings.smtp_configured:
        # DEV ONLY: surface the code in logs when no SMTP is configured.
        logger.warning("DEV ONLY — OTP for %s: %s", to_email, code)
    return sent
