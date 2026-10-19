# FitNest API

Backend API for the **FitNest** Android app (home bodyweight workouts).
Python **FastAPI** + **SQLAlchemy** — SQLite by default, Postgres via `DATABASE_URL`.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | — | `{name, email, password}` → creates user (unverified), sends 6-digit OTP by email |
| POST | `/auth/verify` | — | `{email, code}` → verifies email, returns JWT |
| POST | `/auth/resend-code` | — | `{email}` → resends OTP (max 3/hour per email) |
| POST | `/auth/login` | — | `{email, password}` → JWT (7 days) + `is_admin` flag |
| POST | `/auth/forgot-password` | — | `{email}` → sends reset OTP (always 200) |
| POST | `/auth/reset-password` | — | `{email, code, new_password}` |
| GET | `/auth/me` | Bearer | Current user profile |
| DELETE | `/auth/me` | Bearer | Delete own account |
| GET | `/admin/users?page=&per_page=` | Admin | Paginated user list |
| GET | `/admin/stats` | Admin | Totals + signups last 7/30 days |
| POST | `/ai/chat` | Bearer | FitCoach AI chat: `{message, history?}` → `{reply, remaining_today}` (20/day) |
| GET | `/health` | — | Health check |

Interactive docs: `GET /docs` (Swagger UI).

## Run locally

```bash
cd fitnest-backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit .env (SECRET_KEY, SMTP_*, ...)
uvicorn app.main:app --reload
```

API is then at `http://127.0.0.1:8000`.

> **Dev mode:** if SMTP is not configured, the server logs the OTP code to the
> console (`DEV ONLY — OTP for ...`) instead of sending email, so you can test
> the full flow locally.

## Environment variables

| Var | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Long random string for JWT signing. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | — | Default `sqlite:///./fitnest.db`. For Postgres: `postgresql://user:pass@host:5432/db` |
| `ADMIN_EMAIL` | — | Default `mohmedmaksqoud@gmail.com`. Whoever registers with this email automatically gets `is_admin=true` |
| `SMTP_HOST` / `SMTP_PORT` | ✅ (prod) | e.g. Gmail: `smtp.gmail.com` / `587` (use an **App Password**, not your login password) |
| `SMTP_USER` / `SMTP_PASS` | ✅ (prod) | SMTP credentials |
| `SMTP_FROM` | — | e.g. `FitNest <you@gmail.com>` |
| `SMTP_TLS` | — | `true` (STARTTLS) or `false` (SSL). Default `true` |
| `CORS_ORIGINS` | — | Comma-separated origins, default `*` |
| `APP_NAME` | — | Default `FitNest` (used in emails) |
| `GEMINI_API_KEY` | ✅ (for AI chat) | Google Gemini API key for the FitCoach chat (`POST /ai/chat`). Without it the endpoint returns `503`. Get a free key at https://aistudio.google.com/apikey (see "AI chat" below) |

## AI chat (FitCoach)

`POST /ai/chat` (JWT Bearer required) forwards the user's message to Google
Gemini (`gemini-2.0-flash`) with a FitCoach system prompt (home bodyweight
workouts, Arabic/English, no medical diagnoses). Request:

```json
{ "message": "عايز تمرين صدر في البيت",
  "history": [{ "role": "user", "content": "..." }, { "role": "assistant", "content": "..." }] }
```

`history` is optional (max 10 messages). Response: `{ "reply": "...", "remaining_today": 17 }`.
Rate limit: **20 requests/day per user** (tracked in the `ai_usage` table).

### Getting a free Gemini API key

1. Go to **https://aistudio.google.com/apikey** and sign in with your Google account.
2. Click **"Create API key"** → copy it.
3. Put it in your own `.env` as `GEMINI_API_KEY=...` (locally) or as an
   environment variable on Render/Railway (production).

> **Keep the key to yourself** — it is billed to your Google account. Never
> paste it in chat or commit it to git. Free-tier limits (as of 2025):
> `gemini-2.0-flash` allows roughly **1,500 requests/day** on the free tier —
> plenty for a starter app, and the per-user 20/day cap protects you from abuse.

## Admin seed

The admin account is created simply by **registering with the admin email**
(`ADMIN_EMAIL`, default `mohmedmaksqoud@gmail.com`) — it automatically gets
`is_admin=true`, then verify the OTP and log in. The login response includes
`"is_admin": true`; the Android app uses this flag to show the admin dashboard.

To promote an existing user later:

```bash
python make_admin.py user@example.com
```

## Deploy on Render (free tier)

1. Push this folder to a GitHub repo.
2. Render dashboard → **New → Web Service** → connect the repo.
3. **Build command:** `pip install -r requirements.txt`
   **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. **Add database:** New → PostgreSQL (free trial) → copy its **Internal Database URL** into the web service env var `DATABASE_URL`.
5. **Environment variables:** add `SECRET_KEY` (generate one), `ADMIN_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`.
6. Deploy. Your API base URL will be `https://<your-service>.onrender.com`.

> Note: Render's free web service spins down after ~15 min of inactivity; the
> first request after that takes ~30–60s to wake up.

## Deploy on Railway

1. Push to GitHub → Railway **New Project → Deploy from Repo**.
2. **New → Database → PostgreSQL** → Railway injects `DATABASE_URL` automatically.
3. **Variables** tab: add `SECRET_KEY`, `ADMIN_EMAIL`, SMTP vars.
4. **Settings → Networking → Generate Domain** → your public base URL.
5. Railway uses `$PORT` automatically; the default start command works if you set
   it in **Settings → Deploy → Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## Base URL for the Android app

```
https://<your-service>.onrender.com        (Render)
https://<your-app>.up.railway.app          (Railway)
http://10.0.2.2:8000                       (Android emulator → local dev server)
```

The app must call e.g. `<BASE_URL>/auth/login`, `<BASE_URL>/auth/register`,
`<BASE_URL>/admin/users` (with `Authorization: Bearer <token>`).

## Security notes

- Passwords hashed with **bcrypt**; OTP codes stored as **SHA-256 hashes**, 10-minute expiry, max 5 attempts.
- JWT (HS256) via `python-jose`, 7-day expiry.
- Rate limiting (slowapi) on all OTP/login endpoints + 3/hour resend cap per email.
- No passwords, tokens, or OTP codes are written to logs (dev-mode OTP log only when SMTP is unset).
- Input validation with pydantic (email format, password ≥ 8 chars).
