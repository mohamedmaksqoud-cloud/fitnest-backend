"""Vercel serverless entrypoint: wraps the FastAPI app with Mangum.

Vercel's rewrite behavior delivers the *rewritten* path (/api/index) to the
function and drops the original URL entirely (no header carries it). So we
smuggle the original path through a query parameter (see vercel.json) and
restore it on the event before Mangum builds the ASGI scope.

Vercel's Python event may follow the API Gateway v1 shape
(httpMethod/path/queryStringParameters) or the v2 shape
(version=2.0/rawPath/rawQueryString) — handle both.
"""

from urllib.parse import parse_qsl, urlencode

from mangum import Mangum

from app.main import app

_PATH_PARAM = "__p__"
_base_handler = Mangum(app, lifespan="off")


def _extract(params):
    """Split (key, value) pairs into (original_path_or_None, remaining_pairs)."""
    original = None
    rest = []
    for key, value in params:
        if key == _PATH_PARAM and original is None:
            original = value
        else:
            rest.append((key, value))
    return original, rest


def _restore_v2(event: dict) -> bool:
    qs = event.get("rawQueryString")
    if not qs:
        return False
    original, rest = _extract(parse_qsl(qs, keep_blank_values=True))
    if not original:
        return False
    event["rawPath"] = original
    event["rawQueryString"] = urlencode(rest)
    http = (event.get("requestContext") or {}).get("http")
    if isinstance(http, dict):
        http["path"] = original
    return True


def _restore_v1(event: dict) -> bool:
    qsp = event.get("queryStringParameters") or {}
    original = qsp.get(_PATH_PARAM)
    if not original:
        return False
    event["path"] = original
    remaining = {k: v for k, v in qsp.items() if k != _PATH_PARAM}
    event["queryStringParameters"] = remaining or None
    mvq = event.get("multiValueQueryStringParameters")
    if isinstance(mvq, dict):
        mvq.pop(_PATH_PARAM, None)
        if not mvq:
            event["multiValueQueryStringParameters"] = None
    return True


def handler(event, context):
    _restore_v2(event) or _restore_v1(event)
    return _base_handler(event, context)
