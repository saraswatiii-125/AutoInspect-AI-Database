"""
In-memory sliding-window rate limiter for sensitive authentication endpoints.
Protects against brute-force attacks and credential stuffing without external dependencies.
"""

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Dict, Deque
from fastapi import Request, HTTPException, status
from app.config import settings

class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    Tracks timestamps of recent requests per client identifier.
    """
    def __init__(self):
        self._lock = Lock()
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> tuple[bool, int]:
        """
        Checks whether a request from `key` is allowed under `max_requests` per `window_seconds`.
        Returns (is_allowed, retry_after_seconds).
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            timestamps = self._buckets[key]
            # Prune timestamps outside the current window
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) >= max_requests:
                earliest = timestamps[0]
                retry_after = max(1, int(window_seconds - (now - earliest)) + 1)
                return False, retry_after

            timestamps.append(now)
            return True, 0

    def reset(self):
        """Clears all rate limit buckets (useful between unit tests)."""
        with self._lock:
            self._buckets.clear()

# Global rate limiter instance
limiter = SlidingWindowRateLimiter()

def get_client_ip(request: Request) -> str:
    """Extracts client IP address safely from Request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First IP in X-Forwarded-For list is the original client
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"

class RateLimitDependency:
    """FastAPI dependency for rate-limiting specific route handlers."""
    def __init__(self, key_prefix: str, max_requests: int, window_seconds: int = 60):
        self.key_prefix = key_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(self, request: Request):
        if not settings.RATE_LIMIT_ENABLED:
            return

        ip = get_client_ip(request)
        rate_key = f"{self.key_prefix}:{ip}"

        allowed, retry_after = limiter.is_allowed(
            key=rate_key,
            max_requests=self.max_requests,
            window_seconds=self.window_seconds,
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

