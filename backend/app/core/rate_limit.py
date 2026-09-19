"""Minimal in-process rate limiting for sensitive authentication endpoints.

This is a dependency-free sliding-window limiter sized for a single-process
deployment, which is how this API runs today (`uvicorn ... --reload`). If the
app is ever started with multiple workers or horizontally scaled, move the
counter into Redis (or swap in slowapi) so limits are shared across processes.

Callers are identified by `request.client.host`. Behind a reverse proxy this
is the proxy's address, so either configure the proxy to forward the real
client IP or replace `_client_key` with the trusted forwarded value.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    """Allow at most `max_attempts` actions per `window_seconds` per key."""

    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.max_attempts:
                retry_after = max(1, int(self.window_seconds - (now - hits[0])) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

            hits.append(now)

            # Opportunistic cleanup so abandoned keys cannot grow without bound.
            if len(self._hits) > 1024:
                self._prune(cutoff)

    def _prune(self, cutoff: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[key]


# Brute-force / credential-stuffing protection (per client IP).
_LOGIN_LIMITER = SlidingWindowLimiter(max_attempts=20, window_seconds=300)

# Account-farming protection (per client IP).
_REGISTER_LIMITER = SlidingWindowLimiter(max_attempts=10, window_seconds=3600)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_rate_limit(request: Request) -> None:
    """FastAPI dependency: rate limit POST /auth/login by client IP."""
    _LOGIN_LIMITER.check(_client_key(request))


def register_rate_limit(request: Request) -> None:
    """FastAPI dependency: rate limit POST /auth/register by client IP."""
    _REGISTER_LIMITER.check(_client_key(request))
