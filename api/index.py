"""Vercel serverless entrypoint: wraps the FastAPI app with Mangum.

Two Vercel quirks are handled here:

1. Vercel's rewrite behavior delivers the *rewritten* path (/api/index) to the
   function and drops the original URL entirely (no header carries it). We
   smuggle the original path through a query parameter (see vercel.json) and
   restore it before routing.

2. Vercel's Python event shape is not a clean API Gateway v1/v2 payload, so
   instead of relying on Mangum's format detection we normalize the event
   into a v2-shaped dict ourselves, reading method/path/query/body from every
   plausible location.
"""

from urllib.parse import parse_qsl, urlencode

from mangum import Mangum

from app.main import app

_PATH_PARAM = "__p__"
_base_handler = Mangum(app, lifespan="off")


def _pop_path_param(event):
    """Return (original_path_or_None, remaining_query_string)."""
    qs = event.get("rawQueryString")
    if qs:
        original, rest = None, []
        for key, value in parse_qsl(qs, keep_blank_values=True):
            if key == _PATH_PARAM and original is None:
                original = value
            else:
                rest.append((key, value))
        if original:
            return original, urlencode(rest)
        return None, qs
    qsp = dict(event.get("queryStringParameters") or {})
    if _PATH_PARAM in qsp:
        original = qsp.pop(_PATH_PARAM)
        return original, urlencode(qsp)
    mvq = event.get("multiValueQueryStringParameters") or {}
    vals = mvq.get(_PATH_PARAM)
    if vals:
        original = vals[0] if isinstance(vals, list) else vals
        return original, ""
    return None, ""


def _normalize_event(event):
    original_path, query_string = _pop_path_param(event)

    rc = event.get("requestContext") or {}
    http_ctx = rc.get("http") or {}
    identity = rc.get("identity") or {}

    method = event.get("httpMethod") or http_ctx.get("method") or "GET"
    path = (
        original_path
        or event.get("path")
        or event.get("rawPath")
        or http_ctx.get("path")
        or "/"
    )
    headers = {str(k): str(v) for k, v in (event.get("headers") or {}).items()}
    source_ip = http_ctx.get("sourceIp") or identity.get("sourceIp") or "127.0.0.1"

    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": query_string,
        "headers": headers,
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": http_ctx.get("protocol", "HTTP/1.1"),
                "sourceIp": source_ip,
                "userAgent": headers.get("user-agent", ""),
            },
        },
        "body": event.get("body") or "",
        "isBase64Encoded": bool(event.get("isBase64Encoded")),
    }


def handler(event, context):
    return _base_handler(_normalize_event(event), context)
