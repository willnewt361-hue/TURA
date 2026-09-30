"""Security middleware: headers, rate limiting, CSRF for mutating requests."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_google_maps_api_key, get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _content_security_policy(include_google_maps: bool) -> str:
    script_src = "'self'"
    style_src = "'self' 'unsafe-inline'"
    font_src = "'self' data:"
    img_src = "'self' data: blob:"
    connect_src = "'self' ws: wss:"
    frame_src = "'self'"
    worker_src = ""
    if include_google_maps:
        script_src += (
            " 'unsafe-inline' 'unsafe-eval' https://*.googleapis.com https://*.gstatic.com "
            "https://*.google.com https://*.ggpht.com https://*.googleusercontent.com blob:"
        )
        style_src += " https://fonts.googleapis.com"
        font_src += " https://fonts.gstatic.com"
        img_src += (
            " https://*.googleapis.com https://*.gstatic.com https://*.google.com "
            "https://*.googleusercontent.com"
        )
        connect_src += " https://*.googleapis.com https://*.google.com https://*.gstatic.com data: blob:"
        frame_src += " https://*.google.com"
        worker_src = "worker-src 'self' blob:; "

    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        f"style-src {style_src}; "
        f"font-src {font_src}; "
        f"img-src {img_src}; "
        f"connect-src {connect_src}; "
        f"frame-src {frame_src}; "
        f"{worker_src}"
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(self)"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Content-Security-Policy"] = _content_security_policy(
            bool(get_google_maps_api_key())
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if get_settings().is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory sliding-window rate limiter per IP."""

    def __init__(self, app, limit: int | None = None):
        super().__init__(app)
        self.limit = limit or get_settings().rate_limit_per_minute
        self.window = 60.0
        self.hits: Dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not path.startswith("/api/") or path == "/api/health":
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        now = time.time()
        q = self.hits[client]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )
        q.append(now)
        return await call_next(request)


def check_csrf(request: Request) -> bool:
    """Validate CSRF double-submit cookie for mutating API calls."""
    if request.method in SAFE_METHODS:
        return True
    path = request.url.path
    if not path.startswith("/api/"):
        return True
    # Auth login/register establish session — exempt bootstrap
    if path in ("/api/auth/login", "/api/auth/register", "/api/auth/demo-login"):
        return True
    cookie = request.cookies.get("tura_csrf")
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header:
        return False
    return secrets_compare(cookie, header)


def secrets_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith("/api/") and request.method not in SAFE_METHODS:
            if not check_csrf(request):
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
        return await call_next(request)
