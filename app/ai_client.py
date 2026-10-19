"""Google Gemini client for FitCoach (the in-app AI fitness coach).

Server-side only: the API key lives in the GEMINI_API_KEY env var and is never
sent to clients or written to logs.
"""

import logging

import httpx

from app.config import settings

log = logging.getLogger("fitnest.ai")

SYSTEM_PROMPT = (
    "You are FitCoach, the friendly fitness coach inside the FitNest app "
    "(home bodyweight workouts, no equipment). "
    "Answer in the same language the user writes in (Arabic or English). "
    "Keep answers short and practical: exercises, nutrition, motivation. "
    "Never give medical diagnoses; for injuries/pain advise seeing a professional."
)

MODEL = "gemini-2.0-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
TIMEOUT_SECONDS = 25.0
MAX_OUTPUT_TOKENS = 600


class AIProviderError(Exception):
    """Raised when the Gemini API call fails for any reason."""


def _to_gemini_role(role: str) -> str:
    return "model" if role == "assistant" else "user"


def generate_reply(message: str, history: list[tuple[str, str]] | None = None) -> str:
    """Ask Gemini for a FitCoach reply. Raises AIProviderError on any failure."""
    contents: list[dict] = []
    for role, content in history or []:
        contents.append(
            {"role": _to_gemini_role(role), "parts": [{"text": content}]}
        )
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.7,
        },
    }

    try:
        # NOTE: the API key travels in the query string over HTTPS; it is never logged.
        resp = httpx.post(
            API_URL,
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        log.warning("Gemini request timed out after %ss", TIMEOUT_SECONDS)
        raise AIProviderError("timeout") from exc
    except httpx.HTTPError as exc:
        log.warning("Gemini request failed: %s", type(exc).__name__)
        raise AIProviderError("http_error") from exc

    if resp.status_code != 200:
        # Log status + a short snippet only — never the URL (it holds the key).
        snippet = resp.text[:300].replace("\n", " ")
        log.warning("Gemini API error: status=%s body=%s", resp.status_code, snippet)
        raise AIProviderError(f"status_{resp.status_code}")

    try:
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        reply = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        log.warning("Gemini response had unexpected shape")
        raise AIProviderError("bad_response") from exc

    if not reply:
        log.warning("Gemini returned an empty reply")
        raise AIProviderError("empty_reply")
    return reply
