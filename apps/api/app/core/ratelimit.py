"""Sliding-window rate limiter for sensitive endpoints (login, registration, device ingestion)."""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.errors import AppError


class RateLimiter:
    # ponytail: in-process memory, so limits are per API process. Move to Redis if the API is scaled out.
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_s: int) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                retry = int(window_s - (now - q[0])) + 1
                raise AppError(429, "RATE_LIMITED", f"Too many attempts. Try again in {retry} seconds.", {"retry_after_s": retry})
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Behind the Next.js proxy the first X-Forwarded-For hop is the browser. It is spoofable, so every
    # limit keyed on IP is paired with a limit keyed on something the caller cannot vary (e.g. the account).
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"
