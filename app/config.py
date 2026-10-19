"""Application configuration loaded from environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Core ---
    SECRET_KEY: str = "dev-secret-change-me-in-production"
    DATABASE_URL: str = "sqlite:///./fitnest.db"
    ADMIN_EMAIL: str = "mohmedmaksqoud@gmail.com"  # email that auto-becomes admin on registration
    APP_NAME: str = "FitNest"

    # --- SMTP ---
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = ""
    SMTP_TLS: bool = True

    # --- CORS ---
    CORS_ORIGINS: str = "*"

    # --- AI (FitCoach chat via Google Gemini) ---
    # Free key from https://aistudio.google.com/apikey — the user owns this key
    # himself and puts it in his own .env / hosting env vars (never in chat).
    GEMINI_API_KEY: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()] or ["*"]

    @property
    def sqlalchemy_url(self) -> str:
        url = self.DATABASE_URL.strip()
        # Render/Heroku-style postgres:// -> SQLAlchemy expects postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASS)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.GEMINI_API_KEY.strip())


settings = Settings()
