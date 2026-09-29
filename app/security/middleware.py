"""Security middleware: headers, rate limiting, CSRF for mutating requests."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(self)"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
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
