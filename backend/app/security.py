"""Lightweight hardening for the prototype: security headers, request size cap, per-IP rate limits.

In production these move to the API gateway / WAF; the in-process versions keep the demo safe on a laptop.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CSP = ("default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
       "connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
MAX_BODY = 8 * 1024 * 1024  # KYC photos are capped at this size; JSON bodies are tiny

# (path prefix, method) -> (requests, window seconds), per client IP
LIMITS: list[tuple[str, str, int, int]] = [
    ("/api/advisor/sessions", "POST", 60, 60),     # chat messages and new sessions
    ("/api/kyc/cases", "POST", 40, 60),            # uploads, evaluations
    ("/api/channels/", "POST", 60, 60),            # messaging webhook
    ("/api/quotes", "POST", 30, 60),               # quotes and orders
]


class RateLimiter:
    def __init__(self) -> None:
        self.hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: tuple[str, str], limit: int, window: int) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


limiter = RateLimiter()


def _enabled() -> bool:
    return os.getenv("APNASAATHI_RATE_LIMIT", "1") != "0"


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        if _enabled():
            ip = request.client.host if request.client else "unknown"
            for prefix, method, limit, window in LIMITS:
                if request.method == method and request.url.path.startswith(prefix):
                    if not limiter.allow((ip, prefix), limit, window):
                        return JSONResponse({"detail": "Too many requests, please wait a minute."},
                                            status_code=429, headers={"Retry-After": str(window)})
                    break
        resp = await call_next(request)
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            h.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
        return resp
