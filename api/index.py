"""Vercel serverless entrypoint: wraps the FastAPI app with Mangum.

Vercel's rewrite behavior delivers the *rewritten* path (/api/index) to the
function and drops the original URL entirely (no header carries it). So we
smuggle the original path through a query parameter (see vercel.json) and
restore it on the event before Mangum builds the ASGI scope.
"""

from urllib.parse import parse_qsl, urlencode

from mangum import Mangum

from app.main import app

_PATH_PARAM = "__p__"
_base_handler = Mangum(app, lifespan="off")


def _restore_path(event: dict) -> None:
    qs = event.get("rawQueryString", "")
    if not qs:
        return
    params = parse_qsl(qs, keep_blank_values=True)
    original = None
    rest = []
    for key, value in params:
        if key == _PATH_PARAM and original is None:
            original = value
        else:
            rest.append((key, value))
    if not original:
        return
    event["rawPath"] = original
    event["rawQueryString"] = urlencode(rest)
    http = (event.get("requestContext") or {}).get("http")
    if isinstance(http, dict):
        http["path"] = original


def handler(event, context):
    _restore_path(event)
    return _base_handler(event, context)
